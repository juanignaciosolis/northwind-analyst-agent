import logging
from pathlib import Path
import psycopg2
from psycopg2 import sql
from src.settings import settings
from src.utils.logger import setup_logger

setup_logger()
logger = logging.getLogger(__name__)

DB_DIR = Path(__file__).resolve().parent / "db"
DW_SCHEMA_SQL_PATH = DB_DIR / "schema.sql"
DW_SEED_SQL_PATH = DB_DIR / "seed.sql"
MEMORY_SCHEMA_SQL_PATH = DB_DIR / "memory_schema.sql"

DW_SCHEMA = "northwind"
DW_TABLES = ["sales", "product", "customer", "city", "state"]
DW_SEED_CHECK_TABLE = "sales"

MEMORY_SCHEMA = "agent_memory"
MEMORY_TABLES = ["memory"]


def _tables_exist(cursor, schema: str, tables: list[str]) -> bool:
    cursor.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = %s
          AND table_name = ANY(%s);
        """,
        (schema, tables),
    )
    existing = {row[0] for row in cursor.fetchall()}
    return set(tables).issubset(existing)


def _table_has_rows(cursor, schema: str, table: str) -> bool:
    query = sql.SQL("SELECT EXISTS (SELECT 1 FROM {}.{} LIMIT 1);").format(
        sql.Identifier(schema),
        sql.Identifier(table),
    )
    cursor.execute(query)
    return bool(cursor.fetchone()[0])


def _run_sql_file(cursor, path: Path, label: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"No se encontró el archivo SQL para '{label}': {path}")
    logger.info(f"Ejecutando {label} desde '{path.name}'...")
    sql_content = path.read_text(encoding="utf-8")
    if sql_content.strip():
        cursor.execute(sql_content)


def init_database() -> None:
    conn = None
    try:
        conn = psycopg2.connect(
            host=settings.db_host,
            database=settings.db_name,
            user=settings.db_user,
            password=settings.get_db_password(),
            port=settings.db_port,
            options="-c search_path=northwind,agent_memory,public",
        )
        conn.autocommit = False

        with conn.cursor() as cursor:
            # 1. Schema y tabla de memoria persistente
            if _tables_exist(cursor, MEMORY_SCHEMA, MEMORY_TABLES):
                logger.info("La tabla 'agent_memory.memory' ya existe. Se omite memory_schema.sql.")
            else:
                _run_sql_file(cursor, MEMORY_SCHEMA_SQL_PATH, "schema de memoria")

            # 2. Tablas del DW en schema `northwind`
            if _tables_exist(cursor, DW_SCHEMA, DW_TABLES):
                logger.info(f"Las tablas en '{DW_SCHEMA}' ya existen. Se omite schema.sql.")
            else:
                _run_sql_file(cursor, DW_SCHEMA_SQL_PATH, "DDL del DW")

            # 3. Carga inicial del DW en schema `northwind`
            if _table_has_rows(cursor, DW_SCHEMA, DW_SEED_CHECK_TABLE):
                logger.info(
                    f"La tabla '{DW_SCHEMA}.{DW_SEED_CHECK_TABLE}' ya tiene datos. Se omite seed.sql."
                )
            else:
                _run_sql_file(cursor, DW_SEED_SQL_PATH, "seed del DW")

        conn.commit()
        
        with conn.cursor() as verify_cur:
            verify_cur.execute("SELECT COUNT(*) FROM northwind.sales;")
            sales_count = verify_cur.fetchone()[0]

            verify_cur.execute("SELECT COUNT(*) FROM agent_memory.memory;")
            memory_count = verify_cur.fetchone()[0]

        summary_msg = (
            f"OK | Inicialización completa: schema 'northwind' listo "
            f"({sales_count} filas en sales) y 'agent_memory.memory' listo "
            f"({memory_count} registros)."
        )
        logger.info(summary_msg)
        print(summary_msg, flush=True)

    except Exception as exc:
        logger.error(f"Error durante la inicialización de la base de datos: {exc}")
        if conn is not None:
            conn.rollback()
        raise
    finally:
        if conn is not None:
            conn.close()

if __name__ == "__main__":
    init_database()