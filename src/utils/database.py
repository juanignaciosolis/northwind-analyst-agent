import logging
from logging import Logger

logger: Logger = logging.getLogger(__name__)

import os
import logging
import psycopg2
from psycopg2 import OperationalError, ProgrammingError, DataError, Error
from psycopg2.extensions import connection as PGConnection
from dotenv import load_dotenv
import pandas as pd

load_dotenv()

class DatabaseManager:
    def __init__(self):
        self.conn = None

    def __enter__(self):
        """Se ejecuta al entrar al bloque 'with'"""
        try:
            self.conn = psycopg2.connect(
                host=os.getenv("DB_HOST"),
                database=os.getenv("DB_NAME"),
                user=os.getenv("DB_USER"),
                password=os.getenv("DB_PASSWORD"),
                port=os.getenv("DB_PORT")
            )
            logger.info(f"Conexión a {os.getenv('DB_NAME')} establecida.")
        except Exception as e:
            logger.error(f"Error de conexión: {e}")
            raise e
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Se ejecuta al salir del bloque 'with', garantizando el cierre"""
        if self.conn:
            self.conn.close()
            logger.info("Conexión a la DB cerrada.")

    def execute(self, query: str, limit: int = 20) -> pd.DataFrame:
        """Gestiona el cursor y las transacciones de forma segura"""
        try:
            with self.conn.cursor() as cursor:
                cursor.execute(query)
                filas = cursor.fetchall()
                columnas = [desc[0] for desc in cursor.description]
                logger.info("Consulta ejecutada con exito!.")
                return pd.DataFrame(filas, columns=columnas).head(limit)
        except Exception as e:
            self.conn.rollback()
            logger.error(f"Error en consulta: {e}")
            raise e

def clean_sql_query(raw_query: str) -> str:
    """
    Limpia los bloques de código Markdown y normaliza los saltos de línea
    para que la query quede en una sola línea plana de texto ejecutable.
    """
    clean_query = raw_query.strip()
    
    if clean_query.startswith("```sql"):
        clean_query = clean_query[6:]
    elif clean_query.startswith("```"):
        clean_query = clean_query[3:]
        
    if clean_query.endswith("```"):
        clean_query = clean_query[:-3]
        
    clean_query = clean_query.strip()
    
    clean_query = clean_query.replace("\n", " ")
    
    while "  " in clean_query:
        clean_query = clean_query.replace("  ", " ")
        
    return clean_query.strip()