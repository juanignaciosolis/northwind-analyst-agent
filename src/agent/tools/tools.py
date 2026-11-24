from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from time import perf_counter, sleep
from typing import Any, Callable, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing_extensions import Self
from psycopg_pool import ConnectionPool
from psycopg.rows import dict_row
import pandas as pd
import uuid
import json
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path
import inspect



from pydantic import BaseModel, Field, ValidationError

from src.agent.artifacts.data_memory import InMemoryDataStore
from src.agent.artifacts.conversation_history import Conversation

from src.agent.skills.skills import SkillLoader
from src.utils.database import create_db_pool
from src.agent.artifacts.permanent_memory import (
    ALLOWED_MEMORY_KINDS,
    MemoryCandidate,
    MemoryScope,
    PostgresMemoryStore,
    evaluate_write,
)


ToolKind = Literal[
    "read",
    "compute",
    "local_write",
    "draft",
    "external_effect",
    "write",
]

Role = Literal["viewer", "support_agent", "admin"]

VALID_TOOL_KINDS = {
    "read", "compute", "local_write", "draft", "external_effect", "write"
}


class ExecutionContext(BaseModel):
    """Contexto confiable construido por la aplicación."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    user_id: str
    role: Any
    workspace_ids: list[str] = Field(default_factory=list)
    allow_drafts: bool = False
    allow_external_writes: bool = False
    run_id: str = "run-local"
    session_id: str 

    db_pool: ConnectionPool | None = Field(default=None, exclude=True)

    skill_loaders: list[SkillLoader] = Field(default_factory=list, exclude=True)

    # Artefacto en memoria excluido de serialización para no romper logs ni trazas
    store: InMemoryDataStore = Field(
        default_factory=InMemoryDataStore, exclude=True
    )

    conversation: Conversation | None = Field(default=None, exclude=True)

    memory_store: PostgresMemoryStore | None = Field(default=None, exclude=True)
    project_id: str = ""
    course_id: str = ""

class ToolCall(BaseModel):
    """Solicitud estructurada propuesta por el modelo/router: Tool + argumentos."""

    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    """Salida estable que el runtime convierte en una Observation."""

    ok: bool
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)

class RetryableToolError(RuntimeError):
    """Marca explícitamente un fallo transitorio que sí admite retry automático."""


AuthorizationGuard = Callable[[ExecutionContext, dict[str, Any]], str | None]


class Tool:
    """Contrato runtime-facing y model-facing de una capacidad del agente."""

    def __init__(
        self,
        name: str,
        description: str,
        kind: ToolKind,
        fn: Callable[[dict], ToolResult],
        args_model: type[BaseModel] | None = None,
        timeout_s: float = 3.0,
        retries: int = 0,
        *,
        backoff_s: float = 0.05,
        idempotent: bool = True,
        visible_roles: set[Role] | None = None,
        authorize: AuthorizationGuard | None = None
    ):
        """Configura una Tool y sus controles operativos.

        Args:
            name: Identificador estable usado en Tool Calls.
            description: Instrucción model-facing sobre propósito y uso.
            kind: Categoría usada por Policy para mínimo privilegio.
            fn: Handler Python que ejecuta la capacidad.
            args_model: Schema Pydantic de entrada; `None` acepta un dict libre.
            timeout_s: Máximo de espera del runtime para una ejecución.
            retries: Cantidad de reintentos para `RetryableToolError`.
            backoff_s: Espera base entre reintentos.
            idempotent: Indica si repetir la operación es seguro.
            visible_roles: Roles que pueden ver la Tool; `None` no agrega filtro.
            authorize: Guard opcional para autorizar una llamada concreta.

        Returns:
            None. Deja configurado el contrato.

        Raises:
            ValueError: Si la configuración operativa es insegura o inválida.
        """
        if kind not in VALID_TOOL_KINDS:
            raise ValueError(f"{name}: kind desconocido: {kind}.")
        if timeout_s <= 0:
            raise ValueError(f"{name}: timeout_s debe ser mayor que 0.")
        if retries < 0:
            raise ValueError(f"{name}: retries no puede ser negativo.")
        if backoff_s < 0:
            raise ValueError(f"{name}: backoff_s no puede ser negativo.")
        if retries > 0 and not idempotent:
            raise ValueError(
                f"{name}: una Tool no idempotente no puede tener retries automáticos "
                "sin una estrategia explícita contra duplicados."
            )

        self.name = name
        self.description = description
        self.kind = kind
        self.fn = fn
        self.args_model = args_model
        self.timeout_s = timeout_s
        self.retries = retries
        self.backoff_s = backoff_s
        self.idempotent = idempotent
        self.visible_roles = visible_roles
        self.authorize_guard = authorize

    @property
    def risk(self) -> str:
        """Devuelve la categoría de riesgo/capacidad usada por la Policy."""
        return self.kind

    def function_declaration(self) -> dict:
        """Construye el contrato model-facing para Function Calling.

        Returns:
            Diccionario con `name`, `description` y JSON Schema de parámetros.

        El handler, los permisos y los controles operativos no se exponen al modelo:
        siguen siendo responsabilidad de la aplicación.
        """
        parameters = (
            self.args_model.model_json_schema()
            if self.args_model
            else {"type": "object", "properties": {}}
        )

        # Los `title` de Pydantic aportan poco al modelo y agregan ruido visual.
        parameters.pop("title", None)
        for prop in parameters.get("properties", {}).values():
            prop.pop("title", None)

        return {
            "name": self.name,
            "description": self.description,
            "parameters": parameters,
        }


class ToolPolicy:
    """Decide qué Tools son visibles y autoriza llamadas concretas."""

    KINDS_BY_ROLE = {
        "viewer": {"read", "compute", "local_write"},
        "support_agent": {
            "read",
            "compute",
            "local_write",
            "draft",
            "external_effect",
        },
        "admin": {
            "read",
            "compute",
            "local_write",
            "draft",
            "external_effect",
            "write",
        },
    }

    def allowed_tools(
        self,
        registry: "ToolRegistry",
        context: ExecutionContext,
    ) -> list[Tool]:
        """Filtra las Tools visibles para un contexto.

        Args:
            registry: Registry completo de capacidades.
            context: Contexto confiable de usuario, rol y flags.

        Returns:
            Lista de Tools que el modelo puede ver en ese contexto.
        """
        return self.allowed_tools_from_list(
            list(registry.tools.values()),
            context,
        )

    def authorize(
        self,
        context: ExecutionContext,
        tool: Tool,
        args: dict[str, Any],
    ) -> str | None:
        """Autoriza una llamada concreta después de validar argumentos.

        Args:
            context: Contexto confiable de ejecución.
            tool: Tool ya resuelta por el Registry.
            args: Argumentos ya validados por Pydantic.

        Returns:
            `None` si la llamada está autorizada; texto explicativo si se rechaza.
        """
        visible = {
            item.name
            for item in self.allowed_tools_from_list([tool], context)
        }
        if tool.name not in visible:
            return "La Tool no está habilitada para este contexto."

        if tool.authorize_guard is not None:
            return tool.authorize_guard(context, args)

        return None

    def allowed_tools_from_list(
        self,
        tools: list[Tool],
        context: ExecutionContext,
    ) -> list[Tool]:
        """Aplica reglas de rol, flags y visibilidad a una lista de Tools.

        Args:
            tools: Capacidades candidatas.
            context: Contexto confiable de ejecución.

        Returns:
            Subconjunto visible según mínimo privilegio.
        """
        allowed_kinds = set(self.KINDS_BY_ROLE[context.role])

        if not context.allow_drafts:
            allowed_kinds.discard("draft")

        if not context.allow_external_writes:
            allowed_kinds.discard("external_effect")
            allowed_kinds.discard("write")

        return [
            tool
            for tool in tools
            if tool.kind in allowed_kinds
            and (
                tool.visible_roles is None
                or context.role in tool.visible_roles
            )
        ]



class ToolRegistry:
    """Registry con availability, validation, authorization, timeout y retry."""

    DEFAULT_ALLOWED_KINDS: set[ToolKind] = {"read", "compute", "local_write"}

    def __init__(self):
        """Crea un registry vacío indexado por nombre de Tool."""
        self.tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Registra una Tool sin permitir nombres duplicados.

        Args:
            tool: Contrato completo que se quiere incorporar.

        Returns:
            None.

        Raises:
            ValueError: Si el nombre ya estaba registrado.
        """
        if tool.name in self.tools:
            raise ValueError(f"Tool duplicada: {tool.name}")
        self.tools[tool.name] = tool

    def available_tools(
        self,
        allowed_kinds: set[str] | None = None,
        *,
        context: ExecutionContext | None = None,
        policy: ToolPolicy | None = None,
    ) -> list[Tool]:
        """Devuelve las Tools visibles por lista de kinds o por Policy.

        Args:
            allowed_kinds: Filtro simple para demos sin contexto. Un set vacío
                significa explícitamente "ninguna Tool".
            context: Contexto confiable, usado junto con `policy`.
            policy: Policy que calcula mínimo privilegio.

        Returns:
            Lista de Tools disponibles para el modo elegido.
        """
        if (context is None) != (policy is None):
            raise ValueError("context y policy deben proporcionarse juntos.")

        if context is not None and policy is not None:
            return policy.allowed_tools(self, context)

        allowed = (
            self.DEFAULT_ALLOWED_KINDS
            if allowed_kinds is None
            else allowed_kinds
        )
        return [
            tool
            for tool in self.tools.values()
            if tool.kind in allowed
        ]

    def function_declarations(
        self,
        allowed_kinds: set[str] | None = None,
        *,
        context: ExecutionContext | None = None,
        policy: ToolPolicy | None = None,
    ) -> list[dict]:
        """Convierte las Tools visibles en declaraciones para el modelo.

        Returns:
            Lista de contratos model-facing; nunca incluye handlers ni permisos.
        """
        return [
            tool.function_declaration()
            for tool in self.available_tools(
                allowed_kinds,
                context=context,
                policy=policy,
            )
        ]

    def run(
        self,
        call: ToolCall,
        allowed_kinds: set[str] | None = None,
        *,
        context: ExecutionContext | None = None,
        policy: ToolPolicy | None = None,
    ) -> ToolResult:
        """Ejecuta un Tool Call atravesando todas las capas del runtime.

        Args:
            call: Nombre y argumentos propuestos por el agente.
            allowed_kinds: Filtro simple para demos sin Policy.
            context: Contexto confiable de ejecución.
            policy: Reglas de availability y authorization.

        Returns:elf.tools: dict[str, Tool]
            `ToolResult` exitoso o un error controlado. Las excepciones esperables
            no escapan al Agent Loop.

        Orden de controles:
            Registry → Availability → Validation → Authorization → Execution.
        """
        if (context is None) != (policy is None):
            raise ValueError("context y policy deben proporcionarse juntos.")

        # 1. Registry: ¿existe?
        tool = self.tools.get(call.tool_name)
        if tool is None:
            return ToolResult(
                ok=False,
                content=f"Tool desconocida: {call.tool_name}",
                metadata={"error_type": "unknown_tool"},
            )

        # 2. Availability: ¿se expone en este contexto?
        if context is not None and policy is not None:
            visible = {
                item.name
                for item in policy.allowed_tools(self, context)
            }
            if tool.name not in visible:
                return ToolResult(
                    ok=False,
                    content=f"Tool no disponible en este contexto: {tool.name}",
                    metadata={
                        "error_type": "unavailable_tool",
                        "role": context.role,
                        "kind": tool.kind,
                    },
                )
        else:
            allowed = (
                self.DEFAULT_ALLOWED_KINDS
                if allowed_kinds is None
                else allowed_kinds
            )
            if tool.kind not in allowed:
                return ToolResult(
                    ok=False,
                    content=f"Tool bloqueada por política: {tool.name}",
                    metadata={
                        "error_type": "forbidden_tool",
                        "kind": tool.kind,
                    },
                )

        # 3. Validation: ¿los argumentos tienen forma válida?
        try:
            args = (
                tool.args_model.model_validate(call.arguments).model_dump()
                if tool.args_model
                else dict(call.arguments)
            )
        except ValidationError as exc:
            return ToolResult(
                ok=False,
                content="Argumentos inválidos",
                metadata={
                    "error_type": "validation_error",
                    "details": exc.errors(include_url=False),
                },
            )

        # 4. Authorization: ¿esta llamada concreta está permitida?
        if context is not None and policy is not None:
            denial = policy.authorize(context, tool, args)
            if denial:
                return ToolResult(
                    ok=False,
                    content=denial,
                    metadata={
                        "error_type": "authorization_error",
                        "tool": tool.name,
                    },
                )

        # 5. Execution. Solo `RetryableToolError` habilita un nuevo intento.
        last_retryable_error: RetryableToolError | None = None

        sig = inspect.signature(tool.fn)
        fn_kwargs = {}
        if "context" in sig.parameters:
            fn_kwargs["context"] = context

        for attempt in range(1, tool.retries + 2):
            if attempt > 1:
                # Backoff exponencial mínimo para recordar C3.
                sleep(tool.backoff_s * (2 ** (attempt - 2)))

            executor = ThreadPoolExecutor(max_workers=1)
            started = perf_counter()

            try:
                future = executor.submit(tool.fn, args, **fn_kwargs)
                raw_result = future.result(timeout=tool.timeout_s)
                elapsed_ms = (perf_counter() - started) * 1000

                # El output contract también se valida. Un handler que devuelve
                # otra forma no debe contaminar el resto del loop.
                try:
                    result = ToolResult.model_validate(raw_result)
                except ValidationError as exc:
                    return ToolResult(
                        ok=False,
                        content=f"Salida inválida de {tool.name}",
                        metadata={
                            "error_type": "output_validation_error",
                            "tool": tool.name,
                            "details": exc.errors(include_url=False),
                        },
                    )

                result.metadata = {
                    **result.metadata,
                    "tool": tool.name,
                    "kind": tool.kind,
                    "attempt": attempt,
                    "latency_ms": round(elapsed_ms, 2),
                    "idempotent": tool.idempotent,
                }
                return result

            except FuturesTimeout:
                # Cancelar la espera NO garantiza detener un thread ya iniciado.
                # El handler debe ser idempotente o diseñarse con cancelación cooperativa.
                # Por eso un timeout nunca se reintenta automáticamente acá.
                future.cancel()
                return ToolResult(
                    ok=False,
                    content=f"Timeout ejecutando {tool.name}",
                    metadata={
                        "error_type": "timeout",
                        "tool": tool.name,
                        "timeout_s": tool.timeout_s,
                        "attempt": attempt,
                    },
                )

            except RetryableToolError as exc:
                last_retryable_error = exc
                if attempt > tool.retries:
                    break

            except Exception as exc:
                # Un error no marcado como transitorio no se repite: podría ser
                # determinístico o esconder un bug del handler.
                return ToolResult(
                    ok=False,
                    content=f"Error controlado: {exc}",
                    metadata={
                        "error_type": type(exc).__name__,
                        "tool": tool.name,
                        "attempt": attempt,
                        "retryable": False,
                    },
                )

            finally:
                executor.shutdown(wait=False, cancel_futures=True)

        return ToolResult(
            ok=False,
            content=f"Se agotaron los retries: {last_retryable_error}",
            metadata={
                "error_type": "retry_exhausted",
                "exception_type": type(last_retryable_error).__name__,
                "tool": tool.name,
                "attempts": tool.retries + 1,
            },
        )


class QuerySchema(BaseModel):
    query: str = Field(
        description="Consulta SQL de solo lectura a ejecutar contra la base de datos."
    )

class SummarizeSchema(BaseModel):
    dataset_id: str | None = Field(
        default=None,
        description="ID del dataset. Si se omite, opera sobre el último generado.",
    )
    describe_numeric: bool = Field(
        default=False,
        description="Devuelve estadísticas descriptivas globales (min, max, mean, median, etc).",
    )
    sort_by: str | None = Field(
        default=None,
        description="Columna para ordenar los datos (opcional).",
    )
    ascending: bool = Field(
        default=False,
        description="Dirección de ordenación (False = Mayor a Menor; True = Menor a Mayor).",
    )
    slice_start: int = Field(
        default=0,
        ge=0,
        description="Índice de fila inicial (0-indexed).",
    )
    slice_end: int = Field(
        default=10,
        ge=1,
        description="Índice de fila final. El máximo permitido es 30 filas de diferencia.",
    )

    @model_validator(mode='after')
    def enforce_slice_limits(self, interval: int = 30) -> Self:
        if self.slice_end <= self.slice_start:
            raise ValueError("slice_end debe ser mayor a slice_start.")
        # Clamp automático: si el LLM pide más de 30 filas, lo truncamos de forma segura
        if (self.slice_end - self.slice_start) > interval:
            self.slice_end = self.slice_start + interval
        return self

ChartType = Literal[
    "multilineas",
    "lineas",
    "pie chart",
    "horizontal bar",
    "horizontal stacker bar",
    "column bar",
    "column stacker bar",
    "area char",
    "multiareachart",
]


class CreateChartSchema(BaseModel):
    dataset_id: str | None = Field(
        default=None,
        description="ID del dataset guardado en memoria. Si se omite, toma el último generado.",
    )
    chart_type: ChartType = Field(
        description="Tipo de visualización dinámica a generar con Plotly."
    )
    dimensions: list[str] = Field(
        min_length=1,
        description="Lista de una o más columnas categóricas o temporales (ejes, cortes o agrupadores).",
    )
    metrics: list[str] = Field(
        min_length=1,
        description="Lista de una o más columnas numéricas a representar en el gráfico.",
    )
    title: str | None = Field(
        default=None, description="Título principal de la visualización."
    )
    x_label: str | None = Field(
        default=None, description="Etiqueta personalizada para el eje horizontal."
    )
    y_label: str | None = Field(
        default=None, description="Etiqueta personalizada para el eje vertical."
    )
    filter_column: str | None = Field(
        default=None,
        description="Columna categórica para construir un selector interactivo (dropdown) en el gráfico.",
    )
    hover_columns: list[str] | None = Field(
        default=None,
        description="Columnas adicionales para enriquecer el tooltip dinámico al pasar el cursor.",
    )

def execute_query_tool(
    args: QuerySchema | dict[str, Any], context: ExecutionContext | None = None
) -> ToolResult:

    if context is None or context.db_pool is None:
        return ToolResult(
            ok=False,
            content="Error crítico: No hay un pool de base de datos configurado en el contexto.",
            metadata={"error_type": "NoDatabasePoolError", "name": "execute_query_tool"}
        )
    
    params = QuerySchema.model_validate(args)
    query = params.query

    try:
        with context.db_pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query)
                filas = cur.fetchall()
                columnas = [desc[0] for desc in cur.description]
                df = pd.DataFrame(filas, columns=columnas)

        # 1. Guardar el DataFrame completo en el DataStore desacoplado
        dataset_id = "ds_ephemeral"
        if context is not None and hasattr(context, "store"):
            dataset_id = context.store.add(df=df, query=query, session_id= context.session_id)

        total_rows = len(df)
        THRESHOLD_ROWS = 24

        # 2. Lógica híbrida basada en volumen de filas
        if total_rows <= THRESHOLD_ROWS:
            payload = {
                "dataset_id": dataset_id,
                "total_rows": total_rows,
                "columns": columnas,
                "data": df.to_dict(orient="records"),
                "status": "complete_data",
                "message": "Datos completos disponibles."
            }
        else:
            payload = {
                "dataset_id": dataset_id,
                "total_rows": total_rows,
                "columns": columnas,
                "status": "metadata_only",
                "message": (
                    f"Dataset guardado en memoria. "
                    f"Para ver estadísticas o filas específicas, usa 'summarize_dataframe_tool' con dataset_id='{dataset_id}'."
                ),
            }

        return ToolResult(
            ok=True,
            content=json.dumps(payload, default=str),
            metadata={
                "dataset_id": dataset_id,
                "total_rows_fetched": total_rows,
                "columns": columnas,
                "name": "execute_query_tool",
                "status": payload["status"],
            },
        )

    except Exception as e:
        return ToolResult(
            ok=False,
            content=f"Error al ejecutar la consulta: {e}",
            metadata={
                "error_type": type(e).__name__,
                "name": "execute_query_tool",
            },
        )

def summarize_dataframe_tool(
    args: SummarizeSchema | dict[str, Any], context: ExecutionContext | None = None
) -> ToolResult:
    args = SummarizeSchema.model_validate(args)

    if context is None or not hasattr(context, "store"):
        return ToolResult(
            ok=False,
            content="Error: No hay contexto de ejecución disponible.",
            metadata={"error_type": "NoContextAvailable", "name": "summarize_dataframe_tool"},
        )

    target_dataset_id = args.dataset_id

    df = context.store.get(session_id=context.session_id, dataset_id=target_dataset_id)
    if df is None:
        session_ids = list(
            getattr(context.store, "_storage", {}).get(context.session_id, {}).keys()
        )
        return ToolResult(
            ok=False,
            content=(
                f"Dataset '{target_dataset_id}' no encontrado en la sesión '{context.session_id}'. "
                f"IDs disponibles en la sesión: {session_ids}"
            ),
        )

    if df.empty:
        return ToolResult(ok=False, content="El dataset está vacío (0 filas).")

    try:
        results: dict[str, Any] = {
            "dataset_id": target_dataset_id,
            "source_total_rows": len(df),
            "columns": list(df.columns),
        }

        # 1. Estadísticas Descriptivas (Opcional)
        if args.describe_numeric:
            numeric_cols = df.select_dtypes(include=["number"])
            if not numeric_cols.empty:
                results["descriptive_statistics"] = (
                    numeric_cols.describe().T.round(2).to_dict(orient="index")
                )
            else:
                results["descriptive_statistics"] = "No hay columnas numéricas."

        # 2. Ordenamiento (Opcional)
        view_df = df.copy()
        if args.sort_by:
            if args.sort_by in view_df.columns:
                view_df = view_df.sort_values(by=args.sort_by, ascending=args.ascending)
            else:
                return ToolResult(
                    ok=False,
                    content=f"La columna '{args.sort_by}' no existe. Válidas: {list(view_df.columns)}"
                )

        # 3. Slicing (Cortar el dataframe)
        # Pandas .iloc maneja muy bien si slice_end supera el tamaño real del dataframe
        sliced_df = view_df.iloc[args.slice_start : args.slice_end]
        
        results["data_slice"] = {
            "showing_rows": f"Desde índice {args.slice_start} hasta {args.slice_start + len(sliced_df)}",
            "data": sliced_df.to_dict(orient="records")
        }

        return ToolResult(
            ok=True,
            content=json.dumps(results, default=str, ensure_ascii=False),
            metadata={"dataset_id": target_dataset_id, "name": "summarize_dataframe_tool"},
        )

    except Exception as e:
        return ToolResult(ok=False, content=f"Error inspeccionando el dataframe: {e}")


def create_plotly_chart_tool(
    args: CreateChartSchema, context: ExecutionContext | None = None
) -> ToolResult:

    args = CreateChartSchema.model_validate(args)

    if context is None or not hasattr(context, "store"):
        return ToolResult(
            ok=False,
            content="Error: No existe un contexto de ejecución activo.",
            metadata={"error_type": "NoContextAvailable",
                      "name": "create_plotly_chart_tool"},
        )

    # 1. Recuperar el DataFrame
    df = context.store.get(dataset_id=args.dataset_id, session_id= context.session_id)
    if df is None:
        valid_ids = context.store.list_ids()
        return ToolResult(
            ok=False,
            content=f"Dataset '{args.dataset_id}' no encontrado. IDs disponibles: {valid_ids}",
            metadata={"error_type": "DatasetNotFound",
                      "name": "create_plotly_chart_tool"},
        )

    # 2. Validar columnas requeridas
    check_cols = args.dimensions + args.metrics
    if args.filter_column:
        check_cols.append(args.filter_column)
    if args.hover_columns:
        check_cols.extend(args.hover_columns)

    missing = [c for c in check_cols if c not in df.columns]
    if missing:
        return ToolResult(
            ok=False,
            content=f"Las siguientes columnas no existen en el dataset: {set(missing)}",
            metadata={"error_type": "ColumnNotFoundError",
                      "name": "create_plotly_chart_tool"},
        )

    # 3. Preparación de variables de diseño
    color_palette = px.colors.qualitative.Bold
    labels = {}
    if args.x_label:
        labels["x"] = args.x_label
    if args.y_label:
        labels["y"] = args.y_label

    dim_primary = args.dimensions[0]
    # Si hay filter_column, esa actúa como partición/color primario para permitir el filtrado
    dim_color = args.filter_column or (
        args.dimensions[1] if len(args.dimensions) > 1 else None
    )

    metric_primary = args.metrics[0]
    metric_list = args.metrics

    # Configuración de datos para el hover tooltip
    hover_dict = {}
    if args.hover_columns:
        for col in args.hover_columns:
            hover_dict[col] = True

    try:
        # 4. Construcción según chart_type
        if args.chart_type == "lineas":
            fig = px.line(
                df,
                x=dim_primary,
                y=metric_primary,
                color=dim_color,
                color_discrete_sequence=color_palette,
                hover_data=hover_dict or None,
                labels=labels,
                title=args.title,
            )

        elif args.chart_type == "multilineas":
            if len(metric_list) > 1 and not dim_color:
                fig = px.line(
                    df,
                    x=dim_primary,
                    y=metric_list,
                    color_discrete_sequence=color_palette,
                    hover_data=hover_dict or None,
                    labels=labels,
                    title=args.title,
                )
            else:
                fig = px.line(
                    df,
                    x=dim_primary,
                    y=metric_primary,
                    color=dim_color,
                    color_discrete_sequence=color_palette,
                    hover_data=hover_dict or None,
                    labels=labels,
                    title=args.title,
                )

        elif args.chart_type == "pie chart":
            fig = px.pie(
                df,
                names=dim_primary,
                values=metric_primary,
                color=dim_color,
                color_discrete_sequence=color_palette,
                hover_data=hover_dict or None,
                title=args.title,
            )
            fig.update_traces(
                textposition="inside",
                textinfo="percent+label",
                hovertemplate="<b>%{label}</b><br>Valor: %{value:,.2f}<br>Participación: %{percent}<extra></extra>",
            )

        elif args.chart_type == "column bar":
            fig = px.bar(
                df,
                x=dim_primary,
                y=metric_primary,
                color=dim_color,
                color_discrete_sequence=color_palette,
                hover_data=hover_dict or None,
                labels=labels,
                title=args.title,
            )

        elif args.chart_type == "column stacker bar":
            y_param = (
                metric_list
                if (len(metric_list) > 1 and not dim_color)
                else metric_primary
            )
            fig = px.bar(
                df,
                x=dim_primary,
                y=y_param,
                color=dim_color,
                barmode="stack",
                color_discrete_sequence=color_palette,
                hover_data=hover_dict or None,
                labels=labels,
                title=args.title,
            )

        elif args.chart_type == "horizontal bar":
            fig = px.bar(
                df,
                x=metric_primary,
                y=dim_primary,
                color=dim_color,
                orientation="h",
                color_discrete_sequence=color_palette,
                hover_data=hover_dict or None,
                labels=labels,
                title=args.title,
            )

        elif args.chart_type == "horizontal stacker bar":
            x_param = (
                metric_list
                if (len(metric_list) > 1 and not dim_color)
                else metric_primary
            )
            fig = px.bar(
                df,
                x=x_param,
                y=dim_primary,
                color=dim_color,
                orientation="h",
                barmode="stack",
                color_discrete_sequence=color_palette,
                hover_data=hover_dict or None,
                labels=labels,
                title=args.title,
            )

        elif args.chart_type == "area char":
            fig = px.area(
                df,
                x=dim_primary,
                y=metric_primary,
                color=dim_color,
                color_discrete_sequence=color_palette,
                hover_data=hover_dict or None,
                labels=labels,
                title=args.title,
            )

        elif args.chart_type == "multiareachart":
            y_param = (
                metric_list
                if (len(metric_list) > 1 and not dim_color)
                else metric_primary
            )
            fig = px.area(
                df,
                x=dim_primary,
                y=y_param,
                color=dim_color,
                color_discrete_sequence=color_palette,
                hover_data=hover_dict or None,
                labels=labels,
                title=args.title,
            )

        # 5. Generación del Selector/Filtro Interactivo (updatemenus)
        # Si se especificó una columna de filtro y existen múltiples trazas generadas
        updatemenus = []
        if args.filter_column and len(fig.data) > 1:
            buttons = [
                dict(
                    label="Todos",
                    method="update",
                    args=[
                        {"visible": [True] * len(fig.data)},
                        {
                            "title": (
                                f"{args.title or ''} (Filtro: Todos)"
                                if args.title
                                else "Todos"
                            )
                        },
                    ],
                )
            ]

            for i, trace in enumerate(fig.data):
                # Máscara booleana para aislar únicamente la traza seleccionada
                visibility_mask = [False] * len(fig.data)
                visibility_mask[i] = True
                buttons.append(
                    dict(
                        label=trace.name,
                        method="update",
                        args=[
                            {"visible": visibility_mask},
                            {
                                "title": (
                                    f"{args.title or ''} - {trace.name}"
                                    if args.title
                                    else trace.name
                                )
                            },
                        ],
                    )
                )

            updatemenus.append(
                dict(
                    type="dropdown",
                    direction="down",
                    showactive=True,
                    x=0.0,
                    xanchor="left",
                    y=1.18,
                    yanchor="top",
                    pad={"r": 10, "t": 10},
                    buttons=buttons,
                )
            )

        # 6. Formato de Tooltips y Estilo Global
        # Si no es pie chart, aseguramos tooltip interactivo con formato de miles y decimales
        if args.chart_type != "pie chart":
            for trace in fig.data:
                # Si es barra horizontal, X es la métrica numérica; si no, es Y
                if "orientation" in trace and trace.orientation == "h":
                    trace.hovertemplate = (
                        "<b>%{y}</b><br>"
                        + f"{args.x_label or metric_primary}: "
                        + "<b>%{x:,.2f}</b><extra></extra>"
                    )
                else:
                    trace.hovertemplate = (
                        "<b>%{x}</b><br>"
                        + f"{args.y_label or metric_primary}: "
                        + "<b>%{y:,.2f}</b><extra></extra>"
                    )

        # Ajuste visual general
        fig.update_layout(
            template="plotly_white",
            hovermode="closest",
            hoverlabel=dict(
                bgcolor="rgba(255, 255, 255, 0.95)",
                font_size=13,
                font_color="#111827",
                font_family="Arial, sans-serif",
                bordercolor="#d1d5db",
            ),
            margin=dict(l=40, r=40, t=80 if updatemenus else 60, b=40),
            updatemenus=updatemenus if updatemenus else None,
            legend=dict(
                orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1
            ),
        )

        # 7. Persistir en disco
        artifacts_dir = Path(__file__).resolve().parent.parent / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        chart_id = f"chart_{uuid.uuid4().hex[:8]}"
        file_path = artifacts_dir / f"{chart_id}.html"
        fig.write_html(str(file_path), include_plotlyjs="cdn")

        response_payload = {
            "status": "success",
            "chart_id": chart_id,
            "chart_type": args.chart_type,
            "artifact_path": str(file_path),
            "filter_applied": bool(args.filter_column),
            "message": (
                f"Gráfico generado exitosamente en '{file_path}' "
                f"con selector interactivo y tooltips dinámicos."
            ),
        }

        return ToolResult(
            ok=True,
            content=json.dumps(response_payload),
            metadata={
                "chart_id": chart_id,
                "file_path": str(file_path),
                "dataset_id": args.dataset_id,
                "has_filter": bool(args.filter_column),
                "name": "create_plotly_chart_tool",
            },
        )

    except Exception as e:
        return ToolResult(
            ok=False,
            content=f"Error al generar el gráfico con Plotly: {e}",
            metadata={"error_type": type(e).__name__,
                      "name": "create_plotly_chart_tool"},
        )


class LoadSkillSchema(BaseModel):
    skill_name: str = Field(
        ...,
        description="Nombre exacto de la skill a cargar (ej: 'northwind-analytics')."
    )

    reason: str = Field(
        ...,
        min_length=10,
        max_length=150,
        description="Breve explicación de por qué se requiere cargar esta skill en este momento del flujo."
    )

class LoadResourceSchema(BaseModel):
    skill_name: str = Field(
        ...,
        description="Nombre exacto de la skill dueña del recurso."
    )
    relative_path: str = Field(
        ...,
        description="Ruta relativa del recurso dentro de la skill (ej: 'references/dw-star-schema.md')."
    )

    reason: str = Field(
        ...,
        min_length=10,
        max_length=150,
        description="Breve explicación de por qué se necesita leer este recurso de referencia en este paso."
    )


def load_skill_instructions_tool(
    args: LoadSkillSchema | dict[str, Any], 
    context: ExecutionContext | None = None
) -> ToolResult:
    """Carga únicamente el cuerpo de instrucciones de una Agent Skill buscando en los loaders configurados."""
    params = LoadSkillSchema.model_validate(args)
    
    try:
        loaders = getattr(context, "skill_loaders", [])
        if not loaders:
            return ToolResult(
                ok=False,
                content="Error crítico: No hay skill_loaders configurados en el contexto de ejecución.",
                metadata={"error_type": "NoSkillLoadersError", "name": "load_skill_instructions_tool"}
            )

        skill_data = None
        # Iteramos sobre la lista de loaders para encontrar la skill
        for loader in loaders:
            try:
                skill_data = loader.load(params.skill_name)
                break  # Si la encuentra y carga con éxito, salimos del ciclo
            except (ValueError, FileNotFoundError):
                continue  # Si no está en este loader, probamos con el siguiente

        if not skill_data:
            return ToolResult(
                ok=False,
                content=f"Skill '{params.skill_name}' no encontrada en ninguno de los loaders disponibles.",
                metadata={"error_type": "SkillNotFoundError", "name": "load_skill_instructions_tool"}
            )

        instructions_text = skill_data.get("instructions", "")

        return ToolResult(
            ok=True,
            content=instructions_text,
            metadata={
                "name": "load_skill_instructions_tool",
                "skill": params.skill_name,
                "status": "success"
            }
        )

    except Exception as e:
        return ToolResult(
            ok=False,
            content=f"Error al cargar la skill '{params.skill_name}': {e}",
            metadata={"error_type": type(e).__name__, "name": "load_skill_instructions_tool"}
        )


def load_skill_reference_tool(
    args: LoadResourceSchema | dict[str, Any], 
    context: ExecutionContext | None = None
) -> ToolResult:
    """Lee y devuelve únicamente el contenido de un recurso buscando en los loaders configurados."""
    params = LoadResourceSchema.model_validate(args)

    try:
        loaders = getattr(context, "skill_loaders", [])
        if not loaders:
            return ToolResult(
                ok=False,
                content="Error crítico: No hay skill_loaders configurados en el contexto de ejecución.",
                metadata={"error_type": "NoSkillLoadersError", "name": "load_skill_reference_tool"}
            )

        content_text = None
        # Iteramos sobre la lista de loaders para encontrar el recurso
        for loader in loaders:
            try:
                content_text = loader.load_resource(params.skill_name, params.relative_path)
                break  # Si lo encuentra, salimos del ciclo
            except (ValueError, FileNotFoundError):
                continue  # Si no está en este loader, probamos con el siguiente

        if content_text is None:
            return ToolResult(
                ok=False,
                content=f"Recurso '{params.relative_path}' de la skill '{params.skill_name}' no encontrado en ningún loader.",
                metadata={"error_type": "ResourceNotFoundError", "name": "load_skill_reference_tool"}
            )

        return ToolResult(
            ok=True,
            content=content_text,
            metadata={
                "name": "load_skill_reference_tool",
                "skill": params.skill_name,
                "resource": params.relative_path,
                "status": "success"
            }
        )

    except Exception as e:
        return ToolResult(
            ok=False,
            content=f"Error al leer el recurso '{params.relative_path}' de la skill '{params.skill_name}': {e}",
            metadata={"error_type": type(e).__name__, "name": "load_skill_reference_tool"}
        )


MemoryKind = Literal[
    "user_preference",
    "business_rule",
    "user_correction",
    "kpi_definition",
    "analysis_pattern",
]


class RecallMemoryArgs(BaseModel):
    query: str | None = Field(
        default=None,
        description="Texto o palabra clave para buscar en `key` o en el contenido de memoria.",
    )
    kinds: list[MemoryKind] | None = Field(
        default=None,
        description=(
            "Lista opcional de tipos a filtrar: user_preference, business_rule, "
            "user_correction, kpi_definition, analysis_pattern."
        ),
    )
    limit: int = Field(default=5, ge=1, le=20)


class SaveMemoryArgs(BaseModel):
    kind: MemoryKind = Field(...)
    key: str = Field(..., min_length=1)
    value: Any = Field(...)
    source: str = Field(default="user_explicit")
    confirmed: bool = Field(default=True)
    durable: bool = Field(default=True)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    priority: int = Field(default=5, ge=1, le=10)
    allow_duplicate_key: bool = Field(default=False)


class SupersedeMemoryArgs(BaseModel):
    old_memory_id: str = Field(..., min_length=1)
    kind: MemoryKind = Field(...)
    key: str = Field(..., min_length=1)
    value: Any = Field(...)
    source: str = Field(default="user_correction")
    confirmed: bool = Field(default=True)
    durable: bool = Field(default=True)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    priority: int = Field(default=5, ge=1, le=10)


def _normalize_value(value: Any) -> Any:
    if isinstance(value, str):
        stripped = value.strip()
        if (stripped.startswith("{") and stripped.endswith("}")) or (
            stripped.startswith("[") and stripped.endswith("]")
        ):
            try:
                return json.loads(stripped)
            except json.JSONDecodeError:
                return value
    return value


def _resolve_memory_store(context: ExecutionContext) -> PostgresMemoryStore:
    if context.memory_store is not None:
        return context.memory_store
    if context.db_pool is not None:
        return PostgresMemoryStore(pool=context.db_pool, schema="agent_memory")
    raise ValueError("No hay `memory_store` ni `db_pool` configurado en el contexto.")


def _build_scope(context: ExecutionContext) -> MemoryScope:
    project_id = context.project_id or (
        context.workspace_ids[0] if context.workspace_ids else ""
    )
    return MemoryScope(
        user_id=context.user_id,
        project_id=str(project_id),
        course_id=str(context.course_id or ""),
        session_id=str(context.session_id or ""),
    )


def recall_memory_tool(
    args: RecallMemoryArgs | dict[str, Any],
    context: ExecutionContext | None = None,
) -> ToolResult:
    tool_name = "recall_memory_tool"
    if context is None or (context.memory_store is None and context.db_pool is None):
        return ToolResult(
            ok=False,
            content="Error crítico: No hay `memory_store` ni `db_pool` configurado en el contexto.",
            metadata={"error_type": "NoMemoryStoreError", "name": tool_name},
        )

    try:
        params = RecallMemoryArgs.model_validate(args)
        store = _resolve_memory_store(context)
        scope = _build_scope(context)

        normalized_kinds = (
            {k.strip() for k in params.kinds if isinstance(k, str) and k.strip()}
            if params.kinds
            else None
        )

        memories = store.retrieve(
            scope=scope,
            query=params.query,
            kinds=normalized_kinds,
            limit=params.limit,
        )

        payload = {
            "status": "ok",
            "count": len(memories),
            "memories": memories,
        }
        return ToolResult(
            ok=True,
            content=json.dumps(payload, default=str),
            metadata={
                "count": len(memories),
                "name": tool_name,
            },
        )
    except Exception as exc:
        return ToolResult(
            ok=False,
            content=f"Error al recuperar memoria: {exc}",
            metadata={"error_type": type(exc).__name__, "name": tool_name},
        )


def save_memory_tool(
    args: SaveMemoryArgs | dict[str, Any],
    context: ExecutionContext | None = None,
) -> ToolResult:
    """Guarda una nueva memoria durable y confirmada en `agent_memory.memory`."""
    tool_name = "save_memory_tool"
    if context is None or (context.memory_store is None and context.db_pool is None):
        return ToolResult(
            ok=False,
            content="Error crítico: No hay `memory_store` ni `db_pool` configurado en el contexto.",
            metadata={"error_type": "NoMemoryStoreError", "name": tool_name},
        )

    try:
        params = SaveMemoryArgs.model_validate(args)
        store = _resolve_memory_store(context)
        scope = _build_scope(context)

        candidate = MemoryCandidate(
            kind=params.kind.strip(),
            key=params.key.strip(),
            value=_normalize_value(params.value),
            source=params.source.strip(),
            confidence=params.confidence,
            priority=params.priority,
            confirmed=params.confirmed,
            durable=params.durable,
            sensitive=False,
            persist_allowed=True,
        )

        decision = evaluate_write(candidate)
        if not decision.allowed:
            payload = {
                "status": "rejected",
                "reason": decision.reason,
                "allowed_kinds": sorted(ALLOWED_MEMORY_KINDS),
                "key": candidate.key,
                "kind": candidate.kind,
            }
            return ToolResult(
                ok=False,
                content=json.dumps(payload, default=str),
                metadata={
                    "error_type": "MemoryPolicyRejected",
                    "name": tool_name,
                },
            )

        if not params.allow_duplicate_key:
            existing_memories = store.retrieve(
                scope=scope,
                kinds={candidate.kind},
                limit=20,
            )
            matching_key = next(
                (
                    m
                    for m in existing_memories
                    if str(m.get("key", "")).strip().lower() == candidate.key.lower()
                ),
                None,
            )
            if matching_key is not None:
                payload = {
                    "status": "duplicate_active_key",
                    "reason": (
                        f"Ya existe una memoria activa con key='{candidate.key}' "
                        f"(memory_id='{matching_key.get('memory_id')}'). "
                        "Usa `supersede_memory_tool` con ese `old_memory_id` para actualizarla."
                    ),
                    "existing_memory": matching_key,
                }
                return ToolResult(
                    ok=False,
                    content=json.dumps(payload, default=str),
                    metadata={
                        "error_type": "DuplicateActiveMemoryKey",
                        "existing_memory_id": matching_key.get("memory_id"),
                        "name": tool_name,
                    },
                )

        saved = store.write(scope=scope, candidate=candidate)
        payload = {
            "status": "saved",
            "memory": saved,
        }
        return ToolResult(
            ok=True,
            content=json.dumps(payload, default=str),
            metadata={
                "memory_id": saved.get("memory_id"),
                "key": saved.get("key"),
                "name": tool_name,
            },
        )
    except Exception as exc:
        return ToolResult(
            ok=False,
            content=f"Error al guardar memoria: {exc}",
            metadata={"error_type": type(exc).__name__, "name": tool_name},
        )

def supersede_memory_tool(
    args: SupersedeMemoryArgs | dict[str, Any],
    context: ExecutionContext | None = None,
) -> ToolResult:
    tool_name = "supersede_memory_tool"
    if context is None or (context.memory_store is None and context.db_pool is None):
        return ToolResult(
            ok=False,
            content="Error crítico: No hay `memory_store` ni `db_pool` configurado en el contexto.",
            metadata={"error_type": "NoMemoryStoreError", "name": tool_name},
        )

    try:
        params = SupersedeMemoryArgs.model_validate(args)
        store = _resolve_memory_store(context)
        scope = _build_scope(context)

        clean_old_id = params.old_memory_id.strip()
        candidate = MemoryCandidate(
            kind=params.kind.strip(),
            key=params.key.strip(),
            value=_normalize_value(params.value),
            source=params.source.strip(),
            confidence=params.confidence,
            priority=params.priority,
            confirmed=params.confirmed,
            durable=params.durable,
            sensitive=False,
            persist_allowed=True,
        )

        decision = evaluate_write(candidate)
        if not decision.allowed:
            payload = {
                "status": "rejected",
                "reason": decision.reason,
                "allowed_kinds": sorted(ALLOWED_MEMORY_KINDS),
                "old_memory_id": clean_old_id,
            }
            return ToolResult(
                ok=False,
                content=json.dumps(payload, default=str),
                metadata={
                    "error_type": "MemoryPolicyRejected",
                    "name": tool_name,
                },
            )

        replaced = store.supersede(
            old_memory_id=clean_old_id,
            scope=scope,
            candidate=candidate,
        )
        payload = {
            "status": "superseded",
            "old_memory_id": clean_old_id,
            "memory": replaced,
        }
        return ToolResult(
            ok=True,
            content=json.dumps(payload, default=str),
            metadata={
                "old_memory_id": clean_old_id,
                "new_memory_id": replaced.get("memory_id"),
                "name": tool_name,
            },
        )
    except LookupError as exc:
        return ToolResult(
            ok=False,
            content=f"No se pudo reemplazar la memoria: {exc}",
            metadata={"error_type": "MemoryNotFoundError", "name": tool_name},
        )
    except Exception as exc:
        return ToolResult(
            ok=False,
            content=f"Error al reemplazar memoria: {exc}",
            metadata={"error_type": type(exc).__name__, "name": tool_name},
        )


if __name__ == "__main__":

    SKILL_ROOT_PATH = Path(__file__).resolve().parent.parent / "skills"

    def show_tool_result(step_name: str, result: ToolResult) -> None:
        """Imprime el resultado formateado sin romper si el contenido es un mensaje de error plano."""
        print(f"\n>>> {step_name}")
        print(f"OK: {result.ok}")
        try:
            parsed = json.loads(result.content)
            print(
                f"Content:\n{json.dumps(parsed, indent=2, ensure_ascii=False)}"
            )
        except (json.JSONDecodeError, TypeError):
            print(f"Content: {result.content}")
        print(f"Metadata: {result.metadata}")

    registry = ToolRegistry()
    policy = ToolPolicy()
    northwind_dw_analytics = SkillLoader(SKILL_ROOT_PATH)

    print(SKILL_ROOT_PATH)

    db_pool = create_db_pool()
    memory_store = PostgresMemoryStore(pool=db_pool, schema="agent_memory")

    viewer_context = ExecutionContext(
        user_id="viewer-demo",
        role="viewer",
        workspace_ids=["support-ops"],
        project_id="northwind",
        allow_drafts=False,
        allow_external_writes=False,
        run_id="c9-viewer-demo",
        session_id="sess-viewer-demo",
        skill_loaders=[northwind_dw_analytics],
        db_pool=db_pool,
        memory_store=memory_store,
    )

    support_agent_context = ExecutionContext(
        user_id="support-agent-demo",
        role="support_agent",
        workspace_ids=["support-ops"],
        project_id="northwind",
        allow_drafts=True,
        allow_external_writes=False,
        run_id="c9-support-agent-demo",
        session_id="sess-support-agent-demo",
        skill_loaders=[northwind_dw_analytics],
        db_pool=db_pool,
        memory_store=memory_store,
    )

    registry.register(
        Tool(
            name="execute_query_tool",
            description=(
                "Ejecuta una consulta SQL SELECT sobre PostgreSQL y persiste el DataFrame "
                "resultante en memoria. Devuelve únicamente el 'dataset_id' asignado para ser "
                "consumido por 'summarize_dataframe_tool' o 'create_plotly_chart_tool'."
            ),
            kind="read",
            fn=execute_query_tool,
            args_model=QuerySchema,
            timeout_s=5.0,
            retries=0,
            backoff_s=0.05,
            idempotent=True,
        )
    )

    registry.register(
        Tool(
            name="summarize_dataframe_tool",
            description=(
                "Calcula métricas sobre un dataset en memoria referenciado por su 'dataset_id'. "
                "Permite aplicar describe_numeric, agregaciones globales (sum, mean, median, min, "
                "max, count, nunique) o agrupaciones por dimensiones (group_by) con límite de filas."
            ),
            kind="read",
            fn=summarize_dataframe_tool,
            args_model=SummarizeSchema,
            timeout_s=5.0,
            retries=0,
            backoff_s=0.05,
            idempotent=True,
        )
    )

    registry.register(
        Tool(
            name="create_plotly_chart_tool",
            description=(
                "Genera gráficos interactivos con Plotly a partir de un 'dataset_id' en memoria. "
                "Soporta multilíneas, líneas, pie chart, barras horizontales/verticales (simples y apiladas) "
                "y áreas. Permite configurar dimensiones, métricas, etiquetas, tooltips y un selector de "
                "filtro interactivo. Exporta el archivo HTML resultante a la carpeta 'artifacts/'."
            ),
            kind="local_write",
            fn=create_plotly_chart_tool,
            args_model=CreateChartSchema,
            timeout_s=10.0,
            retries=0,
            backoff_s=0.05,
            idempotent=False,
        )
    )

    registry.register(
        Tool(
            name="load_skill_instructions_tool",
            description="Carga las instrucciones operativas y flujos de una Agent Skill a partir de su nombre exacto.",
            kind="read",
            fn=load_skill_instructions_tool,
            args_model=LoadSkillSchema,
            timeout_s=10.0,
            retries=0,
            backoff_s=0.05,
            idempotent=True,
        )
    )

    registry.register(
        Tool(
            name="load_skill_reference_tool",
            description="Lee un archivo complementario de referencia o esquema técnico asociado a una skill.",
            kind="read",
            fn=load_skill_reference_tool,
            args_model=LoadResourceSchema,
            timeout_s=10.0,
            retries=0,
            backoff_s=0.05,
            idempotent=True,
        )
    )

    registry.register(
        Tool(
            name="recall_memory_tool",
            description="Recupera memorias activas y durables del usuario para el contexto actual.",
            kind="read",
            fn=recall_memory_tool,
            args_model=RecallMemoryArgs,
            timeout_s=5.0,
            retries=0,
            backoff_s=0.05,
            idempotent=True,
        )
    )

    registry.register(
        Tool(
            name="save_memory_tool",
            description="Guarda una preferencia, regla de negocio, definición de KPI o corrección durable confirmada.",
            kind="local_write",
            fn=save_memory_tool,
            args_model=SaveMemoryArgs,
            timeout_s=5.0,
            retries=0,
            backoff_s=0.05,
            idempotent=False,
        )
    )

    registry.register(
        Tool(
            name="supersede_memory_tool",
            description="Reemplaza atómicamente una memoria activa existente por una nueva versión.",
            kind="local_write",
            fn=supersede_memory_tool,
            args_model=SupersedeMemoryArgs,
            timeout_s=5.0,
            retries=0,
            backoff_s=0.05,
            idempotent=False,
        )
    )

    try:
        # =====================================================================
        # 1. Probar execute_query_tool
        # =====================================================================
        call_query = ToolCall(
            tool_name="execute_query_tool",
            arguments={
                "query": (
                    'SELECT d.year AS "Año", ct.countryname AS "País del cliente", '
                    'ct2.countryname AS "País del proveedor", SUM(s.salesamount) AS "Ventas"\n'
                    "FROM sales s\n"
                    "JOIN date d ON s.orderdatekey = d.datekey\n"
                    "JOIN customer c ON s.customerkey = c.customerkey\n"
                    "JOIN city cy ON cy.citykey = c.citykey\n"
                    "JOIN state st ON st.statekey = cy.statekey\n"
                    "JOIN country ct ON ct.countrykey = st.countrykey\n"
                    "JOIN supplier sp ON sp.supplierkey = s.supplierkey\n"
                    "JOIN city cy2 ON cy2.citykey = sp.citykey\n"
                    "JOIN state st2 ON st2.statekey = cy2.statekey\n"
                    "JOIN country ct2 ON ct2.countrykey = st2.countrykey\n"
                    'GROUP BY d.year, ct.countryname, ct2.countryname\n'
                    'ORDER BY d.year, ct.countryname, ct2.countryname'
                ),
            },
        )

        result_query = registry.run(
            call_query,
            context=support_agent_context,
            policy=policy,
        )
        show_tool_result("[1/3] execute_query_tool", result_query)

        if not result_query.ok:
            raise RuntimeError(
                f"Fallo en execute_query_tool: {result_query.content}"
            )

        dataset_id = json.loads(result_query.content)["dataset_id"]

        # =====================================================================
        # 2. Probar summarize_dataframe_tool
        # =====================================================================
        call_summary = ToolCall(
            tool_name="summarize_dataframe_tool",
            arguments={
                "dataset_id": dataset_id,
                "group_by": ["País del cliente"],
                "aggregations": [
                    {
                        "column": "Ventas",
                        "agg": "sum",
                        "alias": "Ventas_Totales",
                    },
                    {
                        "column": "País del proveedor",
                        "agg": "nunique",
                        "alias": "Proveedores_Unicos",
                    },
                ],
                "sort_by": "Ventas",
                "ascending": False,
                "limit": 5,
            },
        )

        result_summary = registry.run(
            call_summary,
            context=support_agent_context,
            policy=policy,
        )
        show_tool_result(
            f"[2/3] summarize_dataframe_tool sobre '{dataset_id}'",
            result_summary,
        )

        if not result_summary.ok:
            raise RuntimeError(
                f"Fallo en summarize_dataframe_tool: {result_summary.content}"
            )

        # =====================================================================
        # 3. Probar create_plotly_chart_tool
        # =====================================================================
        call_chart = ToolCall(
            tool_name="create_plotly_chart_tool",
            arguments={
                "dataset_id": dataset_id,
                "chart_type": "column bar",
                "dimensions": ["País del cliente"],
                "metrics": ["Ventas"],
                "filter_column": "Año",
                "hover_columns": ["País del proveedor"],
                "title": "Ventas por País del Cliente con Filtro de Año",
                "x_label": "País del Cliente",
                "y_label": "Monto Total de Ventas",
            },
        )

        result_chart = registry.run(
            call_chart,
            context=support_agent_context,
            policy=policy,
        )
        show_tool_result(
            f"[3/3] create_plotly_chart_tool sobre '{dataset_id}'", result_chart
        )

        # =====================================================================
        # 4. Probar load_skill_instructions_tool
        # =====================================================================
        call_skill = ToolCall(
            tool_name="load_skill_instructions_tool",
            arguments={
                "skill_name": "northwind-dw-analytics",
                "reason": "Necesito consultar las instrucciones operativas para guiar el flujo analítico.",
            },
        )

        result_skill = registry.run(
            call_skill,
            context=support_agent_context,
            policy=policy,
        )
        show_tool_result(
            "[4/4] load_skill_instructions_tool sobre 'northwind-dw-analytics'",
            result_skill,
        )

        # =====================================================================
        # 5. Probar load_skill_reference_tool
        # =====================================================================
        call_ref = ToolCall(
            tool_name="load_skill_reference_tool",
            arguments={
                "skill_name": "northwind-dw-analytics",
                "relative_path": "references/dw-star-schema.md",
                "reason": "Necesito verificar las reglas dimensionales y el esquema estrella en PostgreSQL.",
            },
        )

        result_ref = registry.run(
            call_ref,
            context=support_agent_context,
            policy=policy,
        )
        show_tool_result(
            "[4/4] load_skill_reference_tool sobre 'references/dw-star-schema.md'",
            result_ref,
        )

        # =====================================================================
        # 6. Pruebas de memoria persistente (save -> recall -> supersede -> cleanup)
        # =====================================================================

        # 6a. Rechazo por política (durable=False)
        result_mem_rejected = registry.run(
            ToolCall(
                tool_name="save_memory_tool",
                arguments={
                    "kind": "user_preference",
                    "key": "ephemeral_chart_filter",
                    "value": {"year": 2020},
                    "confirmed": True,
                    "durable": False,
                },
            ),
            context=support_agent_context,
            policy=policy,
        )
        show_tool_result("[M1] save_memory_tool rechazado por política", result_mem_rejected)

        # 6b. Guardar memoria durable válida
        result_mem_save = registry.run(
            ToolCall(
                tool_name="save_memory_tool",
                arguments={
                    "kind": "kpi_definition",
                    "key": "ventas_netas",
                    "value": {"formula": "SUM(salesamount)", "currency": "USD"},
                    "source": "user_explicit",
                    "confidence": 0.95,
                    "priority": 8,
                },
            ),
            context=support_agent_context,
            policy=policy,
        )
        show_tool_result("[M2] save_memory_tool válido", result_mem_save)
        if not result_mem_save.ok:
            raise RuntimeError(f"Fallo en save_memory_tool: {result_mem_save.content}")

        saved_memory_id = json.loads(result_mem_save.content)["memory"]["memory_id"]

        # 6c. Recuperar memoria guardada
        result_mem_recall = registry.run(
            ToolCall(
                tool_name="recall_memory_tool",
                arguments={
                    "query": "ventas_netas",
                    "kinds": ["kpi_definition"],
                    "limit": 5,
                },
            ),
            context=support_agent_context,
            policy=policy,
        )
        show_tool_result("[M3] recall_memory_tool", result_mem_recall)

        # 6d. Reemplazar memoria existente con supersede_memory_tool
        result_mem_supersede = registry.run(
            ToolCall(
                tool_name="supersede_memory_tool",
                arguments={
                    "old_memory_id": saved_memory_id,
                    "kind": "kpi_definition",
                    "key": "ventas_netas",
                    "value": {"formula": "SUM(salesamount - discountamount)", "currency": "USD"},
                    "source": "user_correction",
                    "confidence": 1.0,
                    "priority": 9,
                },
            ),
            context=support_agent_context,
            policy=policy,
        )
        show_tool_result("[M4] supersede_memory_tool", result_mem_supersede)
        if not result_mem_supersede.ok:
            raise RuntimeError(f"Fallo en supersede_memory_tool: {result_mem_supersede.content}")

        new_memory_id = json.loads(result_mem_supersede.content)["memory"]["memory_id"]

        # 6e. Verificar que recall_memory_tool devuelve solo la nueva versión activa
        result_mem_recall_after = registry.run(
            ToolCall(
                tool_name="recall_memory_tool",
                arguments={
                    "query": "ventas_netas",
                    "kinds": ["kpi_definition"],
                    "limit": 5,
                },
            ),
            context=support_agent_context,
            policy=policy,
        )
        show_tool_result("[M5] recall_memory_tool tras supersede", result_mem_recall_after)

        # 6f. Limpiar registros de prueba de la tabla agent_memory.memory
        cleanup_scope = MemoryScope(
            user_id=support_agent_context.user_id,
            project_id=support_agent_context.project_id,
            course_id=support_agent_context.course_id,
            session_id=support_agent_context.session_id,
        )
        memory_store.delete(memory_id=new_memory_id, scope=cleanup_scope)
        with db_pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM agent_memory.memory WHERE memory_id IN (%s, %s);",
                    (saved_memory_id, new_memory_id),
                )
            conn.commit()
        print("\n>>> [M6] Limpieza de registros de prueba completada.")

    finally:
        db_pool.close()

    print("\n>>> [DEBUG] SaveMemoryArgs JSON Schema:")
    print(json.dumps(SaveMemoryArgs.model_json_schema(), indent=2, ensure_ascii=False))

    declarations = registry.function_declarations(
        context=support_agent_context,
        policy=policy,
    )
    mem_decls = [
        d for d in declarations
        if isinstance(d, dict) and d.get("name") in {"save_memory_tool", "supersede_memory_tool", "recall_memory_tool"}
    ]
    print("\n>>> [DEBUG] Function declarations registradas para memoria:")
    print(json.dumps(mem_decls, indent=2, ensure_ascii=False, default=str))
