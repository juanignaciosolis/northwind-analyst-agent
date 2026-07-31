from rich.table import Table
from rich import box
import pandas as pd
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
        content_group = Group(metadata, f"[red]Estado:[/ ] {error_msg}")

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
