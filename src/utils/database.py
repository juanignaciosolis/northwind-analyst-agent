from logging import Logger
from src.utils.logger import setup_logger

logger: Logger = setup_logger(name=__name__)


import os
import psycopg2
import pandas as pd
from dotenv import load_dotenv

# Aseguramos la carga de variables de entorno
load_dotenv()


import os
import logging
import psycopg2
from psycopg2 import OperationalError, ProgrammingError, DataError, Error
from dotenv import load_dotenv

load_dotenv()

def execute_query(query: str, limit: int = 20) -> pd.DataFrame:

    connection = None
    try:
        connection = psycopg2.connect(
            host=os.getenv("DB_HOST"),
            database=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            port=os.getenv("DB_PORT")
        )
        
        logger.info(f"Conexion a la DB: {os.getenv('DB_NAME')} exitosa!!")

        with connection.cursor() as cursor:
            cursor.execute(query)
            
            filas = cursor.fetchmany(limit)

            columnas = [desc[0] for desc in cursor.description]

            tabla = pd.DataFrame(filas, columns=columnas)
            
            logger.info(f"Consulta ejecutada  Se recuperaron las primeras {tabla.shape[0]} filas (Límite máximo configurado: {limit}).")
            return tabla
        
    # 1. Error Específico: Falla la conexión (credenciales mal puestas, server apagado, puerto bloqueado)   
    except OperationalError as e:
        logger.error(f"[ERROR DE CONEXIÓN]: No se pudo conectar a PostgreSQL. Verificá tu archivo .env o si el servicio local está activo. Detalle: {e}")
        return pd.DataFrame()

    # 2. Error Específico: Sintaxis SQL incorrecta (alucinaciones del LLM, tablas que no existen, campos mal escritos)
    except ProgrammingError as e:
        logger.error(f"[ERROR DE SINTAXIS/PROGRAMACIÓN SQL]: La query generada por el agente falló estructuralmente. Detalle: {e}")
        return pd.DataFrame()

    # 3. Error Específico: Tipos de datos inválidos (por ejemplo, pasar un string a un campo numérico)
    except DataError as e:
        logger.error(f"[ERROR DE DATOS SQL]: Los tipos de datos o restricciones de la query son inválidos. Detalle: {e}")
        return pd.DataFrame()

    # 4. Captura genérica: Cualquier otro error nativo de psycopg2
    except Error as e:
        logger.error(f"[ERROR DB GENERAL]: Ocurrió un error inesperado en el driver de base de datos. Detalle: {e}")
        return pd.DataFrame()

    # 5. Caída de emergencia: Errores imprevistos de Python
    except Exception as e:
        logger.error(f"[ERROR INESPERADO]: Falla general en el módulo de base de datos. Detalle: {e}")
        return pd.DataFrame()        
    finally:
        # 4. Limpieza de conexiones
        if connection:
            connection.close()

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