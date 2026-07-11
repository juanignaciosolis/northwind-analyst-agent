from logging import Logger
from src.utils.logger import setup_logger

logger: Logger = setup_logger(name=__name__)


from dotenv import load_dotenv
from pathlib import Path
import os

load_dotenv()

from src.core.llm import get_llm_client
from src.utils.database import execute_query


if __name__ == "__main__":

        dir_actual = Path(__file__).resolve().parent
        ruta_prompt = dir_actual / "system_prompt.txt"

        try:
                system_prompt_content = ruta_prompt.read_text(encoding="utf-8").strip()
                logger.info(f"System prompt cargado con éxito desde {ruta_prompt.name}")
        except FileNotFoundError:
                logger.error(f"Error: No se encontró el archivo '{ruta_prompt.name}' en {dir_actual}")
                system_prompt_content = None


        client = get_llm_client(system_prompt = system_prompt_content)
        logger.info("¡Éxito! Cliente instanciado")

        logger.info("\nEnviando mensaje de prueba...")
        respuesta = client.send_message(prompt="Dame los 10 primeros registros de los clientes")

        logger.info(f"Respuesta: {respuesta}")

        execute_query(respuesta.text)

        logger.info("Fin de la prueba")


              
