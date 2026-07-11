from logging import Logger
from src.utils.logger import setup_logger

logger: Logger = setup_logger(name=__name__)

import os
import psycopg2
from dotenv import load_dotenv

# Cargar configuración desde el .env
load_dotenv()

logger.info("Inicialización de la base de datos desde archivo SQL...")

db_host = os.getenv("DB_HOST", "localhost")
db_user = os.getenv("DB_USER")
db_password = os.getenv("DB_PASSWORD")
db_name = os.getenv("DB_NAME")
db_port = os.getenv("DB_PORT", "5432")

SQL_FILE_PATH = "northwind.sql"

if not os.path.exists(SQL_FILE_PATH):
    logger.error(f"No se encontró el archivo '{SQL_FILE_PATH}' en la raíz del proyecto.")
    exit(1)

try:
    # Conectamos al motor de Postgres
    conn = psycopg2.connect(
        host=db_host,
        database=db_name,
        user=db_user,
        password=db_password,
        port=db_port
    )
    conn.autocommit = False  
    cursor = conn.cursor()
    
    logger.info(f"Leyendo el archivo '{SQL_FILE_PATH}'...")

    with open(SQL_FILE_PATH, 'r', encoding='utf-8') as sql_file:
        sql_script = sql_file.read()
        
    logger.info("Ejecutando el esquema y poblando las tablas de forma masiva...")
    
    cursor.execute(sql_script)
    
    conn.commit()

    logger.info("¡Base de datos configurada y poblada con éxito!")
    
    cursor.close()
    conn.close()

except psycopg2.Error as db_err:
    logger.error(f"Ocurrió un error de base de datos en la ejecución de SQL: {db_err}")
    if 'conn' in locals():
        conn.rollback() # Volvemos atrás si algo falló para no corromper el volumen
except Exception as e:
    logger.error(f"Error inesperado: {e}")