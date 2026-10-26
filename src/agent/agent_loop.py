from __future__ import annotations

import time
from typing import Any, Literal

from pydantic import BaseModel, Field

from src.agent.tools.tools import ToolResult
from src.agent.tools.tools import ToolCall
from src.agent.llm import build_provider
from src.agent.llm.contract import LLMProvider

class AgentDecision(BaseModel):
    """Representa la decisión del modelo/router para el próximo paso."""
    action: Literal["tool", "final"]
    tool_name: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    final_answer: str | None = None

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
    user_message: str,
    available_tools: list[dict[str, Any]] | None = None,
    observations: list[ToolResult] | None = None,
) -> AgentDecision:
    
    response = client.generate(prompt=user_message, 
                               available_tools=available_tools, 
                               tool_results=observations)
    return AgentDecision(
        action="tool" if response.executed else "final",
        tool_name=response.tool_name,
        arguments=response.tool_arguments,
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

def run_basic_agent(
    user_message,
    registry,
    decide_next,
    max_steps=4,
    max_seconds=10.0,
    allowed_kinds=None,
    *,
    context=None,
    policy=None,
    max_tool_calls=None,
):
    """Ejecuta Decide → Act → Observe y devuelve respuesta, traza y stop reason.

    `decide_next` recibe el mensaje original y las Observations acumuladas.
    Toda Tool se ejecuta a través del Registry para conservar los controles del runtime.
    """
    observations = []
    trace = []
    started = time.perf_counter()
    tool_calls = 0

    for step in range(1, max_steps + 1):
        if time.perf_counter() - started > max_seconds:
            return {
                "answer": "Se alcanzó el límite de tiempo.",
                "trace": trace,
                "observations": observations,
                "stop_reason": "timeout",
            }

        decision = decide_next(user_message, observations)
        trace.append({
            "run_id": getattr(context, "run_id", None),
            "step": step,
            "event": "decision",
            "decision": sanitize_for_trace(decision.model_dump()),
        })

        if decision.action == "final":
            return {
                "answer": decision.final_answer,
                "trace": trace,
                "observations": observations,
                "stop_reason": "final_answer",
            }

        if max_tool_calls is not None and tool_calls >= max_tool_calls:
            return {
                "answer": "Se alcanzó el presupuesto de Tool Calls.",
                "trace": trace,
                "observations": observations,
                "stop_reason": "budget",
            }

        if not decision.tool_name:
            return {
                "answer": "Decisión inválida: falta tool_name.",
                "trace": trace,
                "observations": observations,
                "stop_reason": "unrecoverable_error",
            }

        result = registry.run(
            ToolCall(
                tool_name=decision.tool_name,
                arguments=decision.arguments,
            ),
            allowed_kinds=allowed_kinds,
            context=context,
            policy=policy,
        )

        tool_calls += 1
        observations.append(result)

        trace.append({
            "run_id": getattr(context, "run_id", None),
            "step": step,
            "event": "observation",
            "tool": decision.tool_name,
            "arguments": sanitize_for_trace(decision.arguments),
            "observation": sanitize_for_trace(result.model_dump()),
        })

    return {
        "answer": "Se alcanzó el máximo de pasos.",
        "trace": trace,
        "observations": observations,
        "stop_reason": "max_steps",
    }

if __name__ == "__main__":