from __future__ import annotations

import time
import json
from typing import Any, Literal
from pathlib import Path
import uuid
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

console = Console()

from pydantic import BaseModel, Field

from src.agent.tools.tools import ToolResult
from src.agent.tools.tools import ToolCall, Tool, ExecutionContext, ToolRegistry, ToolPolicy
from src.agent.tools.tools import execute_query_tool, summarize_dataframe_tool, create_plotly_chart_tool
from src.agent.tools.tools import load_skill_instructions_tool, load_skill_reference_tool
from src.agent.tools.tools import QuerySchema, SummarizeSchema, CreateChartSchema, LoadSkillSchema, LoadResourceSchema
from src.agent.tools.tools import recall_memory_tool, supersede_memory_tool, save_memory_tool, RecallMemoryArgs, SupersedeMemoryArgs, SaveMemoryArgs
from src.agent.skills.skills import SkillLoader
from src.prompts.system_prompt import agent_system_prompt, zero_shot_system_prompt, agent_skills_system_prompt
from src.settings import settings
from src.agent.llm import build_provider
from src.agent.llm.contract import LLMProvider
from contextlib import contextmanager
from src.utils.database import create_db_pool
from src.agent.artifacts.conversation_history import Conversation
from src.agent.artifacts.permanent_memory import PostgresMemoryStore
from src.utils.helpers import log_agent_event, select_session_id



class AgentDecision(BaseModel):
    """Representa la decisión del modelo/router para el próximo paso."""
    action: Literal["tool", "final"]
    tool_name: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    final_answer: str | None = None
    model_content: Any = None

SENSITIVE_MARKERS = {
    "api_key",
    "apikey",
    "secret",
    "token",
    "password",
    "credential",
    "database",
    "password",
    "host",
    "user"
}

def decide_next(
    client: LLMProvider,
    system_prompt: str | None,
    user_message: str,
    available_tools: list[dict[str, Any]] | None = None,
    observations: list[ToolResult] | None = None,
    history: list[dict[str, str]] | None = None,
) -> AgentDecision:
    
    call = client.generate(
        prompt=user_message, 
        system=system_prompt,
        available_tools=available_tools, 
        tool_results=observations,
        history=history
    )
    # Si call ya es el GenerationResult o un wrapper con .result:
    response = getattr(call, "result", call)

    if response.tool_name in {"save_memory_tool", "supersede_memory_tool", "recall_memory_tool"}:
        print(
            "[DEBUG decide_next]",
            "tool_name=", repr(response.tool_name),
            "tool_arguments=", repr(response.tool_arguments),
        )

    # Es tool solo si el modelo efectivamente devolvió el nombre de una herramienta
    is_tool_call = bool(response.tool_name)

    return AgentDecision(
        action="tool" if is_tool_call else "final",
        tool_name=response.tool_name,
        arguments=response.tool_arguments or {},  # Evita enviar None si Pydantic exige dict
        model_content=getattr(response, "model_content", None),
        final_answer=response.final_text,
    )

def sanitize_for_trace(value):
    """Enmascara secretos simples antes de persistir datos en una traza.

    Args:
        value: Valor arbitrario; puede contener dicts o listas anidadas.

    Returns:
        Copia saneada en la que claves sensibles se reemplazan por
        `***REDACTED***`.

    Se aplica solo a observabilidad. El valor original sigue disponible para el
    runtime mientras dure la ejecución.
    """
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            normalized = str(key).lower()
            if any(marker in normalized for marker in SENSITIVE_MARKERS):
                cleaned[key] = "***REDACTED***"
            else:
                cleaned[key] = sanitize_for_trace(item)
        return cleaned
    if isinstance(value, list):
        return [sanitize_for_trace(item) for item in value]
    return value


@contextmanager
def agent_session(
    user_id: str,
    role: str,
    allow_drafts: bool = True,
    allow_external_writes: bool = False,
    skill_loaders: list[SkillLoader] | None = None,
    conversation: Conversation | None = None,
    session_id: str | None = None,
    project_id: str = "",
    course_id: str = "",
):
    """Administrador de contexto que gestiona la infraestructura de la sesión."""
    db_pool = create_db_pool()
    memory_store = PostgresMemoryStore(pool=db_pool, schema="agent_memory")
    try:
        clean_session_id = session_id.strip() if session_id and session_id.strip() else None
        resolved_session_id = (
            clean_session_id
            or (conversation.session_id if conversation else None)
            or f"session_{uuid.uuid4().hex[:8]}"
        )
        conv = conversation or Conversation(session_id=resolved_session_id)
        context = ExecutionContext(
            user_id=user_id,
            session_id=resolved_session_id,
            role=role,
            workspace_ids=["support-ops"],
            project_id=project_id,
            course_id=course_id,
            allow_drafts=allow_drafts,
            allow_external_writes=allow_external_writes,
            run_id=f"run-{user_id}",
            skill_loaders=skill_loaders or [],
            conversation=conv,
            db_pool=db_pool,
            memory_store=memory_store,
        )
        yield context
    finally:
        if db_pool:
            db_pool.close()

def run_basic_agent(
    client: LLMProvider,
    system_prompt: str | None,
    user_message: str,
    registry: ToolRegistry,
    decide_next,
    max_steps: int = 10,
    max_seconds: float = 10.0,
    allowed_kinds=None,
    *,
    context: ExecutionContext | None = None,
    policy: None = None,
    max_tool_calls: int | None = None,
    keep_last_messages: int = 10,
) -> dict[str, Any]:
    """Ejecuta Decide -> Act -> Observe y devuelve respuesta, traza y stop reason."""
    observations: list[ToolResult] = []
    trace: list[dict[str, Any]] = []
    started = time.perf_counter()
    tool_calls = 0

    conv = context.conversation if context is not None else None
    history = conv.as_dicts(keep_last_messages) if conv is not None else None

    available_tools = registry.function_declarations(
        context=context,
        policy=policy,
    )

    for step in range(1, max_steps + 1):
        log_agent_event("step", step=step)

        if time.perf_counter() - started > max_seconds:
            log_agent_event("warn", message="Se alcanzó el límite de tiempo.")
            return {
                "answer": "Se alcanzó el límite de tiempo.",
                "trace": trace,
                "observations": observations,
                "stop_reason": "timeout",
            }

        decision = decide_next(
            client=client,
            system_prompt=system_prompt,
            user_message=user_message,
            available_tools=available_tools,
            observations=observations,
            history=history,
        )
        trace.append({
            "run_id": context.run_id if context is not None else None,
            "step": step,
            "event": "decision",
            "decision": sanitize_for_trace(decision.model_dump()),
        })

        if decision.action == "final":
            final_text = decision.final_answer or ""
            log_agent_event("final", message=final_text)

            if conv is not None and final_text.strip():
                conv.add("user", user_message)
                conv.add("assistant", final_text)
                if len(conv.messages) > keep_last_messages:
                    conv.compact(keep_last=keep_last_messages)

            return {
                "answer": final_text,
                "trace": trace,
                "observations": observations,
                "stop_reason": "final_answer",
            }

        if max_tool_calls is not None and tool_calls >= max_tool_calls:
            log_agent_event("warn", message="Se alcanzó el presupuesto de Tool Calls.")
            return {
                "answer": "Se alcanzó el presupuesto de Tool Calls.",
                "trace": trace,
                "observations": observations,
                "stop_reason": "budget",
            }

        if not decision.tool_name:
            log_agent_event("warn", message="Decisión inválida: falta tool_name.")
            return {
                "answer": "Decisión inválida: falta tool_name.",
                "trace": trace,
                "observations": observations,
                "stop_reason": "unrecoverable_error",
            }

        log_agent_event(
            "tool_call",
            tool_name=decision.tool_name,
            arguments=decision.arguments,
        )
        result = registry.run(
            ToolCall(
                tool_name=decision.tool_name,
                arguments=decision.arguments,
            ),
            allowed_kinds=allowed_kinds,
            context=context,
            policy=policy,
        )

        if result.metadata is None:
            result.metadata = {}
        result.metadata["name"] = decision.tool_name
        result.metadata["arguments"] = decision.arguments
        result.metadata["model_content"] = decision.model_content

        tool_calls += 1
        observations.append(result)

        log_agent_event(
            "tool_result",
            tool_name=decision.tool_name,
            result=result,
        )
        trace.append({
            "run_id": context.run_id if context is not None else None,
            "step": step,
            "event": "observation",
            "tool": decision.tool_name,
            "arguments": sanitize_for_trace(decision.arguments),
            "observation": sanitize_for_trace(result.model_dump()),
        })

    log_agent_event("warn", message="Se alcanzó el máximo de pasos.")
    return {
        "answer": "Se alcanzó el máximo de pasos.",
        "trace": trace,
        "observations": observations,
        "stop_reason": "max_steps",
    }

if __name__ == "__main__":

    SKILL_DIR = Path(__file__).parent / "skills"

    system_prompt_content = agent_skills_system_prompt()

    northwind_dw_analytics = SkillLoader(SKILL_DIR)

    client = build_provider(settings)

    registry = ToolRegistry()
    policy = ToolPolicy()

    registry.register(
        Tool(
            name="execute_query_tool",
            description=(
                "Ejecuta consultas SQL SELECT y guarda el resultado en memoria. "
                "Devuelve los datos completos si son pocas filas (<= 24) o un 'dataset_id' en modo 'metadata_only' si el volumen es mayor."
                "Usala cuando necesites obtener y procesar datos de Northwind"
            ),
            kind="read",
            fn=execute_query_tool,
            args_model=QuerySchema,
            timeout_s=30000,
            retries=0,
            backoff_s=0.05,
            idempotent=True,
        )
    )

    registry.register(
        Tool(
            name="summarize_dataframe_tool",
            description=(
                "Inspecciona un dataset en memoria. Permite ver estadísticas globales (describe), "
                "ordenar por una columna (sort_by) y extraer un rango específico de filas (slice_start y slice_end)."
                "Usala cuando 'execute_query_tool' no devuelva los datos completos"
            ),
            kind="read",
            fn=summarize_dataframe_tool,
            args_model=SummarizeSchema,
            timeout_s=30000,
            retries=0,
            backoff_s=0.05,
            idempotent=True,
        )
    )

    registry.register(
        Tool(
            name="create_plotly_chart_tool",
            description=(
                "Genera un gráfico interactivo a partir de un 'dataset_id' en memoria. "
                "Consulta previamente la guía de selección de gráficos de la skill para parametrizarlo correctamente." 
                "Usala cuando el cliente te pida un grafico"
            ),
            kind="local_write",
            fn=create_plotly_chart_tool,
            args_model=CreateChartSchema,
            timeout_s=30000,
            retries=0,
            backoff_s=0.05,
            idempotent=False,
        )
    )

    registry.register(
        Tool(
            name="load_skill_instructions_tool",
            description=("Carga las instrucciones operativas y flujos de una skill a partir de su nombre exacto."
                         "Usala cuando necesites enteder como realizar una tarea compleja, analisis a pedido del usuario"),
            kind="read",
            fn=load_skill_instructions_tool,
            args_model=LoadSkillSchema,
            timeout_s=300000,
            retries=0,
            backoff_s=0.05,
            idempotent=True,
        )
    )

    registry.register(
        Tool(
            name="load_skill_reference_tool",
            description=("Lee un archivo complementario de referencia o esquema técnico asociado a una skill."
                         "Usa esta tool cuando necesites instrucciones, definiciones, esquemas, recursos o informacion adicional"),
            kind="read",
            fn=load_skill_reference_tool,
            args_model=LoadResourceSchema,
            timeout_s=30000,
            retries=0,
            backoff_s=0.05,
            idempotent=True,
        )
    )

    registry.register(
        Tool(
            name="recall_memory_tool",
            description=(
                "Recupera memorias activas y durables del usuario como ser preferencias, reglas de negocio, "
                "definiciones de KPI, correcciones o patrones de análisis"
                "Usala cuando necesites conocer prefencias, reglas de negocio, correcciones, definiciones impartidas por el usuario"
            ),
            kind="read",
            fn=recall_memory_tool,
            args_model=RecallMemoryArgs,
            timeout_s=30000,
            retries=0,
            backoff_s=0.05,
            idempotent=True,
        )
    )

    registry.register(
        Tool(
            name="save_memory_tool",
            description=(
                "Guarda una nueva memoria durable como ser preferencias, reglas de negocio, "
                "definiciones de KPI o correcciones."
                "Usala cuando necesites guardar una nueva preferencia, regla de negocio, correccion o definicion hecha por el usuario"
            ),
            kind="local_write",
            fn=save_memory_tool,
            args_model=SaveMemoryArgs,
            timeout_s=30000,
            retries=0,
            backoff_s=0.05,
            idempotent=False,
        )
    )

    registry.register(
        Tool(
            name="supersede_memory_tool",
            description=(
                "Reemplaza una memoria activa existente por una nueva versión "
                "cuando el usuario corrige o actualiza una regla, KPI o preferencia."
                "Usala cuando necesites reemplazar una preferencia, regla de negocio, correccion o definicion vieja por una nueva del usuario"
            ),
            kind="local_write",
            fn=supersede_memory_tool,
            args_model=SupersedeMemoryArgs,
            timeout_s=30000,
            retries=0,
            backoff_s=0.05,
            idempotent=False,
        )
    )

    EXIT_COMMANDS = {"salir", "exit", "quit", "q", ":q"}

    known_sessions: list[str] = []
    selected_session_id = select_session_id(known_sessions)

    with agent_session(
        user_id="support-agent-demo",
        role="support_agent",
        skill_loaders=[northwind_dw_analytics],
        project_id="northwind",
        session_id= selected_session_id
    ) as support_agent_context:
        console.print(
            Panel.fit(
                f"[bold cyan]Chat Northwind Analyst[/bold cyan]\n"
                f"Sesión: [bold]{selected_session_id}[/bold]\n"
                f"Escribí [bold]salir[/bold] para terminar.",
                border_style="cyan",
            )
        )

        turn = 0
        while True:
            try:
                user_input = console.input("\n[bold blue]Vos > [/bold blue]").strip()
            except (KeyboardInterrupt, EOFError):
                console.print("\n[dim]Sesión finalizada.[/dim]")
                break

            if not user_input:
                continue

            if user_input.lower() in EXIT_COMMANDS:
                console.print("[dim]Cerrando sesión... ¡Hasta luego![/dim]")
                break

            turn += 1
            console.print(f"[dim]Turno {turn}[/dim]")

            agent_run = run_basic_agent(
                client,
                system_prompt=system_prompt_content,
                user_message=user_input,
                registry=registry,
                decide_next=decide_next,
                max_steps=20,
                max_seconds=100000,
                context=support_agent_context,
                policy=policy,
                max_tool_calls=10,
            )

            if agent_run["stop_reason"] != "final_answer":
                console.print(
                    f"[yellow]Stop reason:[/yellow] {agent_run['stop_reason']}"
                )