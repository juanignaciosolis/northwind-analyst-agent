from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from time import perf_counter, sleep
from typing import Any, Callable, Literal
from pydantic import BaseModel, ConfigDict, Field
from src.utils.database import pool
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

    # Artefacto en memoria excluido de serialización para no romper logs ni trazas
    store: InMemoryDataStore = Field(
        default_factory=InMemoryDataStore, exclude=True
    )


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


AggFunction = Literal[
    "sum", "mean", "median", "min", "max", "count", "nunique"
]


class AggregationSpec(BaseModel):
    column: str = Field(description="Columna sobre la cual calcular la métrica.")
    agg: AggFunction = Field(description="Operación de agregación a aplicar.")
    alias: str | None = Field(
        default=None, description="Nombre de la columna resultante (opcional)."
    )


class SummarizeSchema(BaseModel):
    dataset_id: str | None = Field(
        default=None,
        description="ID del dataset (ej: 'ds_a1b2c3d4'). Si se omite, opera sobre el último generado.",
    )
    group_by: list[str] | None = Field(
        default=None,
        description="Columnas categóricas para agrupar (ej: ['country', 'status']).",
    )
    aggregations: list[AggregationSpec] = Field(
        default_factory=list,
        description="Lista de métricas a calcular sobre columnas del dataset.",
    )
    describe_numeric: bool = Field(
        default=False,
        description="Si es True, calcula estadísticas descriptivas completas para columnas numéricas.",
    )
    limit: int = Field(
        default=15,
        ge=1,
        le=50,
        description="Límite de filas si se realiza un group_by.",
    )
    sort_by: str | None = Field(
        default=None,
        description="Columna o alias para ordenar antes de truncar.",
    )
    ascending: bool = Field(
        default=False,
        description="Dirección de la ordenación (False = descendente).",
    )

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
    args: QuerySchema, context: ExecutionContext | None = None
) -> ToolResult:
    query = args.query if isinstance(args, QuerySchema) else args.get("query", "")

    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query)
                filas = cur.fetchall()
                columnas = [desc[0] for desc in cur.description]
                df = pd.DataFrame(filas, columns=columnas)

        # 1. Guardar en el DataStore desacoplado
        dataset_id = "ds_ephemeral"
        if context is not None and hasattr(context, "store"):
            dataset_id = context.store.add(df=df, query=query)

        # 2. Preview de 10 filas
        top_10 = df.head(10).to_dict(orient="records")

        # 3. Respuesta para la observación del LLM
        payload = {
            "dataset_id": dataset_id,
            "total_rows": len(df),
            "columns": columnas
            }

        return ToolResult(
            ok=True,
            content=json.dumps(payload, default=str),
            metadata={
                "dataset_id": dataset_id,
                "total_rows_fetched": len(df),
                "columns": columnas,
                "name": "execute_query_tool",
            },
        )

    except Exception as e:
        return ToolResult(
            ok=False,
            content=f"Error al ejecutar la consulta: {e}",
            metadata={"error_type": type(e).__name__,
                      "name": "execute_query_tool"},
        )

def summarize_dataframe_tool(
    args: SummarizeSchema, context: ExecutionContext | None = None
) -> ToolResult:

    args = SummarizeSchema.model_validate(args)

    if context is None or not hasattr(context, "store"):
        return ToolResult(
            ok=False,
            content="Error: No hay contexto de ejecución disponible.",
            metadata={"error_type": "NoContextAvailable",
                      "name": "summarize_dataframe_tool"},
        )

    # 1. Obtener DataFrame del almacén
    df = context.store.get(args.dataset_id)
    if df is None:
        valid_ids = context.store.list_ids()
        return ToolResult(
            ok=False,
            content=f"No se encontró el dataset '{args.dataset_id}'. IDs en memoria: {valid_ids}",
            metadata={"error_type": "DatasetNotFound",
                      "name": "summarize_dataframe_tool"},
        )

    if df.empty:
        return ToolResult(
            ok=False,
            content="El dataset solicitado está vacío (0 filas).",
            metadata={"error_type": "EmptyDataframeError",
                      "name": "summarize_dataframe_tool"},
        )

    try:
        results: dict[str, Any] = {
            "dataset_id": args.dataset_id or "latest",
            "source_rows": len(df),
        }

        # 2. Estadísticas descriptivas numéricas
        if args.describe_numeric:
            numeric_cols = df.select_dtypes(include=["number"])
            if not numeric_cols.empty:
                results["descriptive_statistics"] = (
                    numeric_cols.describe().T.round(2).to_dict(orient="index")
                )
            else:
                results["descriptive_statistics"] = (
                    "No hay columnas numéricas en el dataset."
                )

        # 3. Agregaciones y agrupaciones
        if args.aggregations:
            cols_needed = [agg.column for agg in args.aggregations]
            if args.group_by:
                cols_needed.extend(args.group_by)

            missing = [c for c in cols_needed if c not in df.columns]
            if missing:
                return ToolResult(
                    ok=False,
                    content=f"Columnas no encontradas en el dataset: {set(missing)}",
                    metadata={"error_type": "ColumnNotFoundError",
                              "name": "summarize_dataframe_tool"},
                )

            # Caso A: Group By
            if args.group_by:
                agg_dict: dict[str, list[str]] = {}
                rename_map: dict[tuple[str, str], str] = {}

                for agg in args.aggregations:
                    agg_dict.setdefault(agg.column, []).append(agg.agg)
                    if agg.alias:
                        rename_map[(agg.column, agg.agg)] = agg.alias

                grouped = df.groupby(args.group_by).agg(agg_dict)

                if isinstance(grouped.columns, pd.MultiIndex):
                    grouped.columns = [
                        rename_map.get((c, f), f"{c}_{f}")
                        for c, f in grouped.columns
                    ]

                grouped = grouped.reset_index()

                if args.sort_by and args.sort_by in grouped.columns:
                    grouped = grouped.sort_values(
                        by=args.sort_by, ascending=args.ascending
                    )

                results["grouped_summary"] = {
                    "group_by": args.group_by,
                    "total_groups": len(grouped),
                    "showing_top": min(len(grouped), args.limit),
                    "data": grouped.head(args.limit).to_dict(orient="records"),
                }

            # Caso B: Agregación Global
            else:
                global_metrics: dict[str, Any] = {}
                for agg in args.aggregations:
                    series = df[agg.column]

                    if agg.agg == "sum":
                        val = series.sum()
                    elif agg.agg == "mean":
                        val = series.mean()
                    elif agg.agg == "median":
                        val = series.median()
                    elif agg.agg == "min":
                        val = series.min()
                    elif agg.agg == "max":
                        val = series.max()
                    elif agg.agg == "count":
                        val = series.count()
                    elif agg.agg == "nunique":
                        val = series.nunique()
                    else:
                        continue

                    key = agg.alias if agg.alias else f"{agg.column}_{agg.agg}"
                    global_metrics[key] = (
                        round(float(val), 4)
                        if isinstance(val, (int, float))
                        else val
                    )

                results["global_metrics"] = global_metrics

        return ToolResult(
            ok=True,
            content=json.dumps(results, default=str),
            metadata={
                "dataset_id": args.dataset_id,
                "source_rows": len(df),
                "name": "summarize_dataframe_tool",
            },
        )

    except Exception as e:
        return ToolResult(
            ok=False,
            content=f"Error durante el resumen analítico: {e}",
            metadata={"error_type": type(e).__name__,
                      "name": "summarize_dataframe_tool"},
        )


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
    df = context.store.get(args.dataset_id)
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

if __name__ == "__main__":

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

    viewer_context = ExecutionContext(
        user_id="viewer-demo",
        role="viewer",
        workspace_ids=["support-ops"],
        allow_drafts=False,
        allow_external_writes=False,
        run_id="c9-viewer-demo",
    )

    support_agent_context = ExecutionContext(
        user_id="support-agent-demo",
        role="support_agent",
        workspace_ids=["support-ops"],
        allow_drafts=True,
        allow_external_writes=False,
        run_id="c9-support-agent-demo",
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

    try:
        # =========================================================================
        # 1. Probar execute_query_tool
        # =========================================================================
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

        # =========================================================================
        # 2. Probar summarize_dataframe_tool
        # =========================================================================
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
                "sort_by": "Ventas_Totales",
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

        # =========================================================================
        # 3. Probar create_plotly_chart_tool
        # =========================================================================
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

    finally:
        pool.close()