import json
from typing import Any
import uuid

from rich import box
from rich.console import Console, Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.prompt import Prompt
import pandas as pd
import sqlparse

console = Console()


def _summarize_tool_output(tool_name: str, content: Any) -> str:
    """Extrae solo el dato útil de cada tool para no inundar la consola."""
    try:
        data = json.loads(content) if isinstance(content, str) else content
    except (json.JSONDecodeError, TypeError):
        text = str(content).strip().replace("\n", " ")
        return text[:100] + ("..." if len(text) > 100 else "")

    if not isinstance(data, dict):
        return str(data)[:100]

    if tool_name == "recall_memory_tool":
        keys = [m.get("key") for m in data.get("memories", [])]
        return f"{data.get('count', 0)} memorias activas {keys if keys else ''}".strip()

    if tool_name in ("save_memory_tool", "supersede_memory_tool"):
        mem = data.get("memory", {})
        return (
            f"status={data.get('status')} | key='{mem.get('key')}' "
            f"(id={mem.get('memory_id')})"
        )

    if tool_name == "execute_query_tool":
        if "dataset_id" in data:
            return f"dataset_id='{data['dataset_id']}' ({data.get('total_rows', '?')} filas)"
        return f"filas devueltas={len(data.get('rows', data))}"

    if tool_name == "summarize_dataframe_tool":
        return f"resumen generado ({len(json.dumps(data))} chars)"

    if tool_name == "create_plotly_chart_tool":
        return (
            f"gráfico exportado en "
            f"{data.get('file_path', data.get('output_path', 'artifacts/'))}"
        )

    if tool_name in ("load_skill_instructions_tool", "load_skill_reference_tool"):
        return "recurso cargado"

    return json.dumps(data, ensure_ascii=False)[:100]


def log_agent_event(
    event: str,
    *,
    step: int | None = None,
    tool_name: str | None = None,
    arguments: dict[str, Any] | None = None,
    result: Any | None = None,
    message: str | None = None,
) -> None:
    """Imprime trazas limpias y acotadas del ciclo Decide -> Act -> Observe."""
    if event == "step":
        console.print(f"[dim]── Paso {step} ──[/dim]")

    elif event == "tool_call":
        is_query = tool_name == "execute_query_tool" and isinstance(arguments, dict)
        raw_sql = arguments.get("query") or arguments.get("sql") if is_query else None

        if raw_sql:
            other_args = {
                k: v for k, v in arguments.items() if k not in ("query", "sql")
            }
            extra = f" [dim]{other_args}[/dim]" if other_args else ""
            formatted_sql = sqlparse.format(
                str(raw_sql).strip(),
                reindent=True,
                keyword_case="upper",
            )
            console.print(f"  [cyan]⚙ Tool:[/cyan] [bold]{tool_name}[/bold]{extra}")
            console.print(
                Syntax(formatted_sql, "sql", theme="monokai", word_wrap=True)
            )
        else:
            args_str = ""
            if arguments:
                compact_args = {
                    k: (v if len(str(v)) <= 60 else f"{str(v)[:57]}...")
                    for k, v in arguments.items()
                }
                args_str = f" [dim]{compact_args}[/dim]"
            console.print(f"  [cyan]⚙ Tool:[/cyan] [bold]{tool_name}[/bold]{args_str}")

    elif event == "tool_result" and result is not None:
        meta = getattr(result, "metadata", None) or {}
        latency = meta.get("latency_ms")
        latency_str = f" [dim]({latency} ms)[/dim]" if latency is not None else ""

        if getattr(result, "ok", False):
            summary = _summarize_tool_output(tool_name or "", result.content)
            console.print(f"  [green]✔ OK[/green]{latency_str} → {summary}")
        else:
            if tool_name == "execute_query_tool":
                console.print(
                    Panel(
                        str(result.content).strip(),
                        title=f"[bold red]Error en {tool_name}[/bold red]{latency_str}",
                        border_style="red",
                        padding=(0, 1),
                    )
                )
            else:
                err_preview = str(result.content).splitlines()[0][:120]
                console.print(f"  [red]✖ Error[/red]{latency_str} → {err_preview}")

    elif event == "final":
        console.print(
            Panel(
                Markdown(message or ""),
                title="[bold green]Asistente[/bold green]",
                border_style="green",
                padding=(1, 2),
            )
        )

    elif event == "warn":
        console.print(f"[bold yellow]⚠ {message}[/bold yellow]")



def select_session_id(
    known_sessions: list[str] | None = None,
) -> str:
    """Permite iniciar una sesión nueva o reutilizar un session_id previo."""
    console.print("\n[bold cyan]Sesión[/bold cyan]")
    console.print("[dim]Escribí 'nueva' (o Enter) para una sesión nueva, o elegí/pegá un session_id.[/dim]")

    if known_sessions:
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("#", justify="right", style="dim", width=4)
        table.add_column("Session ID", style="cyan")

        for idx, sid in enumerate(known_sessions, start=1):
            table.add_row(str(idx), sid)
        console.print(table)

    choice = Prompt.ask("[bold blue]Sesión[/bold blue]", default="nueva").strip()

    if not choice or choice.lower() in {"nueva", "new", "n"}:
        return f"session_{uuid.uuid4().hex[:8]}"

    if known_sessions and choice.isdigit():
        idx = int(choice)
        if 1 <= idx <= len(known_sessions):
            return known_sessions[idx - 1]

    return choice

def generate_rich_table(df: pd.DataFrame) -> Table:
    """Convierte un DataFrame en una tabla estética de Rich."""
    table = Table(
        show_header=True,
        header_style="bold cyan",
        box=box.SIMPLE_HEAVY,
        show_lines=True,
    )

    if df is None or not isinstance(df, pd.DataFrame):
        table.add_column("Resultado", justify="center")
        table.add_row("[italic yellow]Sin resultados para mostrar[/]")
        return table

    for col in df.columns:
        justify = "right" if pd.api.types.is_numeric_dtype(df[col]) else "left"
        table.add_column(col, justify=justify)

    for _, row in df.iterrows():
        formatted_row = [
            f"{val:.2f}" if isinstance(val, (float, int)) else str(val)
            for val in row
        ]
        table.add_row(*formatted_row)

    return table


def gerenate_rich_response(response_obj):
    metadata = Table.grid(expand=True)
    metadata.add_column(ratio=1)

    metadata.add_row(f"[bold]Tipo:[/ ] {str(getattr(response_obj, 'type', 'N/A'))}")
    metadata.add_row(
        f"[bold]Confianza:[/ ] {getattr(response_obj, 'confidence', 0) or 0:.2%}"
    )

    is_revision = getattr(response_obj, "human_revision", False)
    metadata.add_row(
        f"[bold]Revision Humana:[/ ] {'[red]Sí[/]' if is_revision else '[green]No[/]'}"
    )

    query = getattr(response_obj, "query", None)

    if query:
        formatted_sql = sqlparse.format(
            query,
            reindent=True,
            keyword_case="upper",
        )
        sql_syntax = Syntax(formatted_sql, "sql", theme="monokai", word_wrap=True)
        content_group = Group(metadata, "[bold cyan]Query:[/]", sql_syntax)
    else:
        error_msg = getattr(response_obj, "error", "Sin detalle disponible")
        resumen_msg = getattr(response_obj, "resumen", "Sin detalle disponible")
        content_group = Group(
            metadata,
            f"[red]Estado:[/ ] {error_msg}",
            f"[yellow]Resumen:[/ ] {resumen_msg}",
        )

    return content_group


def format_sql_query(raw_query: str) -> str:
    if raw_query:
        formatted_sql = sqlparse.format(
            raw_query,
            reindent=True,
            keyword_case="upper",
        )
        syntax = Syntax(formatted_sql, "sql", theme="monokai", line_numbers=False)
        return syntax
    return "No hay consulta SQL para este este resultado"


def imprimir_tabla_evaluacion(resumen: dict) -> None:
    """
    Imprime una tabla elegante en consola con el resumen de evaluación de un agente.

    Args:
        resumen (dict): Diccionario con los campos de métricas y configuración.
    """
    console = Console()

    tabla = Table(
        title="📊 [bold cyan]REPORTE DE EVALUACIÓN DE AGENTE[/bold cyan]",
        box=box.ROUNDED,
        header_style="bold magenta",
        show_header=True,
        title_justify="center",
    )

    tabla.add_column("Métrica / Parámetro", style="bold white", width=25)
    tabla.add_column("Valor", justify="left")
    tabla.add_column("Detalle / Porcentaje", justify="right")

    tabla.add_row(
        "📅 Fecha",
        str(resumen.get("fecha", "-")),
        "[dim]Ejecución[/dim]",
    )
    tabla.add_row(
        "🤖 Proveedor / Modelo",
        f"{resumen.get('provedor', '-')} / [bold green]{resumen.get('modelo', '-')}[/bold green]",
        "[dim]LLM Client[/dim]",
    )
    tabla.add_row(
        "⚡ Latencia Promedio",
        f"[yellow]{resumen.get('latencia_promedio', 0):,.2f} ms[/yellow]",
        "[dim]Tiempo resp.[/dim]",
    )

    sys_prompt = str(resumen.get("system_promt", "-"))
    sys_prompt_corto = sys_prompt[:35] + "..." if len(sys_prompt) > 35 else sys_prompt
    tabla.add_row("🧠 System Prompt", sys_prompt_corto, "[dim]Config[/dim]")

    tabla.add_section()

    tabla.add_row(
        "🧪 Casos Totales",
        f"[bold]{resumen.get('casos', 0)}[/bold]",
        "100.0%",
    )

    aciertos = resumen.get("aciertos", 0)
    precision = resumen.get("precision", 0.0)
    tabla.add_row(
        "✅ Aciertos",
        f"[green]{aciertos}[/green]",
        f"[green bold]{precision*100:.1f}%[/green bold]",
    )

    sin_resp = resumen.get("sin_respuesta", 0)
    p_sin_resp = resumen.get("p_sin_respuesta", 0.0)
    tabla.add_row(
        "🟡 Sin Respuesta",
        f"[yellow]{sin_resp}[/yellow]",
        f"[yellow]{p_sin_resp*100:.1f}%[/yellow]",
    )

    mal_form = resumen.get("mal_formadas", 0)
    p_mal_form = resumen.get("p_mal_formadas", 0.0)
    tabla.add_row(
        "❌ Mal Formadas",
        f"[red]{mal_form}[/red]",
        f"[red]{p_mal_form*100:.1f}%[/red]",
    )

    console.print(tabla)