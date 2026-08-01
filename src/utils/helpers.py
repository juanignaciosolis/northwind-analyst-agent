from rich.table import Table
from rich import box
import pandas as pd
from rich.console import Console
from rich.console import Group
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
import sqlparse # <--- Importa esto

def generate_rich_table(df: pd.DataFrame) -> Table:
    """Convierte un DataFrame en una tabla estética de Rich."""
    
    table = Table(
        show_header=True, 
        header_style="bold cyan", 
        box=box.SIMPLE_HEAVY,
        show_lines=True
    )

    # Agregar columnas
    for col in df.columns:
        # Alineamos a la derecha si es columna numérica, izquierda si es texto
        justify = "right" if pd.api.types.is_numeric_dtype(df[col]) else "left"
        table.add_column(col, justify=justify)

    # Agregar filas
    for _, row in df.iterrows():
        # Formateamos valores: si es float, redondeamos a 2 decimales
        formatted_row = [
            f"{val:.2f}" if isinstance(val, (float, int)) else str(val) 
            for val in row
        ]
        table.add_row(*formatted_row)

    return table

def gerenate_rich_response(response_obj):
    # 1. Creamos la tabla de forma segura usando str() para evitar Nones
    metadata = Table.grid(expand=True)
    metadata.add_column(ratio=1)
    
    # Usamos str(x or "N/A") para prevenir que un None rompa el renderizado
    metadata.add_row(f"[bold]Tipo:[/ ] {str(getattr(response_obj, 'type', 'N/A'))}")
    metadata.add_row(f"[bold]Confianza:[/ ] {getattr(response_obj, 'confidence', 0):.2%}")
    
    is_revision = getattr(response_obj, 'human_revision', False)
    metadata.add_row(f"[bold]Revision Humana:[/ ] {'[red]Sí[/]' if is_revision else '[green]No[/]'}")

    # 2. Construimos el contenido de forma segura
    query = getattr(response_obj, 'query', None)
    
    if query:
        # AQUÍ ESTÁ LA MAGIA:
        # reindent=True: agrega saltos de línea y tabulaciones
        # keyword_case='upper': pone SELECT, JOIN, etc. en mayúsculas
        formatted_sql = sqlparse.format(
            query, 
            reindent=True, 
            keyword_case='upper'
        )
        
        # Ahora pasamos el SQL formateado a Syntax
        sql_syntax = Syntax(formatted_sql, "sql", theme="monokai", word_wrap=True)
        content_group = Group(metadata, "[bold cyan]Query:[/]", sql_syntax)
    else:
        # Si no hay query, mostramos el error o mensaje
        error_msg = getattr(response_obj, 'error', 'Sin detalle disponible')
        resumen_msg = getattr(response_obj, 'resumen', 'Sin detalle disponible')
        content_group = Group(metadata, 
                              f"[red]Estado:[/ ] {error_msg}", 
                              f"[yellow]Resumen:[/ ] {resumen_msg}")

    return content_group

def format_sql_query( raw_query: str)-> str:

    if raw_query:
        # 2. Formatear la SQL (reindentación automática y palabras clave en MAYÚSCULAS)
        formatted_sql = sqlparse.format(
            raw_query, 
            reindent=True, 
            keyword_case='upper'
        )
        
        # 3. Crear el objeto Syntax de Rich para colores
        # theme="monokai" es excelente para SQL en terminales oscuras
        syntax = Syntax(formatted_sql, "sql", theme="monokai", line_numbers=False)
        
        # 4. Imprimir
        return syntax
    else:
        return "No hay consulta SQL para este este resultado"

def imprimir_tabla_evaluacion(resumen: dict) -> None:
    """
    Imprime una tabla elegante en consola con el resumen de evaluación de un agente.
    
    Args:
        resumen (dict): Diccionario con los campos de métricas y configuración.
    """
    console = Console()

    # 1. Crear la tabla con título estilizado
    tabla = Table(
        title="📊 [bold cyan]REPORTE DE EVALUACIÓN DE AGENTE[/bold cyan]",
        box=box.ROUNDED,
        header_style="bold magenta",
        show_header=True,
        title_justify="center"
    )

    # 2. Definir las columnas principales
    tabla.add_column("Métrica / Parámetro", style="bold white", width=25)
    tabla.add_column("Valor", justify="left")
    tabla.add_column("Detalle / Porcentaje", justify="right")

    # --- SECCIÓN 1: CONFIGURACIÓN Y EXPERIMENTO ---
    tabla.add_row(
        "📅 Fecha", 
        str(resumen.get("fecha", "-")), 
        "[dim]Ejecución[/dim]"
    )
    tabla.add_row(
        "🤖 Proveedor / Modelo", 
        f"{resumen.get('provedor', '-')} / [bold green]{resumen.get('modelo', '-')}[/bold green]", 
        "[dim]LLM Client[/dim]"
    )
    tabla.add_row(
        "⚡ Latencia Promedio", 
        f"[yellow]{resumen.get('latencia_promedio', 0):,.2f} ms[/yellow]", 
        "[dim]Tiempo resp.[/dim]"
    )
    
    # Formateamos el system prompt para que no rompa el ancho de la pantalla si es largo
    sys_prompt = str(resumen.get("system_promt", "-"))
    sys_prompt_corto = sys_prompt[:35] + "..." if len(sys_prompt) > 35 else sys_prompt
    tabla.add_row("🧠 System Prompt", sys_prompt_corto, "[dim]Config[/dim]")

    tabla.add_section()  # Línea separadora visual

    # --- SECCIÓN 2: VOLUMEN DE PRUEBAS ---
    tabla.add_row(
        "🧪 Casos Totales", 
        f"[bold]{resumen.get('casos', 0)}[/bold]", 
        "100.0%"
    )
    
    # --- SECCIÓN 3: RESULTADOS Y RENDIMIENTO ---
    aciertos = resumen.get("aciertos", 0)
    precision = resumen.get("precision", 0.0)
    tabla.add_row(
        "✅ Aciertos", 
        f"[green]{aciertos}[/green]", 
        f"[green bold]{precision*100:.1f}%[/green bold]"
    )

    sin_resp = resumen.get("sin_respuesta", 0)
    p_sin_resp = resumen.get("p_sin_respuesta", 0.0)
    tabla.add_row(
        "🟡 Sin Respuesta", 
        f"[yellow]{sin_resp}[/yellow]", 
        f"[yellow]{p_sin_resp*100:.1f}%[/yellow]"
    )

    mal_form = resumen.get("mal_formadas", 0)
    p_mal_form = resumen.get("p_mal_formadas", 0.0)
    tabla.add_row(
        "❌ Mal Formadas", 
        f"[red]{mal_form}[/red]", 
        f"[red]{p_mal_form*100:.1f}%[/red]"
    )

    # 3. Imprimir en consola
    console.print(tabla)