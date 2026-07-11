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

def execute_query(query: str, limit: int = 20) -> list:

    connection = None
    try:
        connection = psycopg2.connect(
            host=os.getenv("DB_HOST"),
            database=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            port=os.getenv("DB_PORT")
        )
        
        logger.info(f"Conexion a la DB: {os.getenv("DB_NAME")} exitosa!!")

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
        return []

    # 2. Error Específico: Sintaxis SQL incorrecta (alucinaciones del LLM, tablas que no existen, campos mal escritos)
    except ProgrammingError as e:
        logger.error(f"[ERROR DE SINTAXIS/PROGRAMACIÓN SQL]: La query generada por el agente falló estructuralmente. Detalle: {e}")
        return []

    # 3. Error Específico: Tipos de datos inválidos (por ejemplo, pasar un string a un campo numérico)
    except DataError as e:
        logger.error(f"[ERROR DE DATOS SQL]: Los tipos de datos o restricciones de la query son inválidos. Detalle: {e}")
        return []

    # 4. Captura genérica: Cualquier otro error nativo de psycopg2
    except Error as e:
        logger.error(f"[ERROR DB GENERAL]: Ocurrió un error inesperado en el driver de base de datos. Detalle: {e}")
        return []

    # 5. Caída de emergencia: Errores imprevistos de Python
    except Exception as e:
        logger.error(f"[ERROR INESPERADO]: Falla general en el módulo de base de datos. Detalle: {e}")
        return []        
    finally:
        # 4. Limpieza de conexiones
        if connection:
            connection.close()