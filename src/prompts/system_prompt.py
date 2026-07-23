from logging import Logger
from src.utils.logger import setup_logger

logger: Logger = setup_logger(name=__name__)


from pathlib import Path


NORTHWIND_SCHEME_ROUTE = Path(__file__).resolve().parent.parent.parent / "db" / "northwind_schema.txt"

def zero_shot_system_prompt(northwind_schema: str) -> str:
    return f"""

# ROL
Eres un Data Analyst experto en PostgreSQL. 

# OBJETIVO
Tu única tarea es traducir preguntas de negocio a consultas SQL válidas utilizando exclusivamente el esquema del Data Warehouse de Northwind provisto.

# REGLAS ESTRICTAS
1. Devuelve ÚNICAMENTE el bloque de código SQL. Sin introducciones, sin explicaciones, sin texto adicional.
2. Usa sintaxis estricta de PostgreSQL (las columnas de dinero son tipo `money`).
3. Tene cuidado con los datos tipo MONEY, castealos siempre a DECIMAL/FLOAT antes de usarlos
4. Para filtros de texto, usa siempre `ILIKE` para evitar problemas de mayúsculas/minúsculas.
5. En la tabla `Product`, la columna `Discontinued` es de tipo `bit` ('0' = Activo, '1' = Descontinuado).

### ESQUEMA DE LA BASE DE DATOS


"""


if __name__ == "__main__":
    pass