from logging import Logger
from src.utils.logger import setup_logger

logger: Logger = setup_logger(name=__name__)


from dotenv import load_dotenv
import os

load_dotenv()

from src.core.llm import get_llm_client


if __name__ == "__main__":
        client = get_llm_client()
        logger.info("¡Éxito! Cliente instanciado")

        logger.info("\nEnviando mensaje de prueba...")
        respuesta = client.send_message(prompt="Hola soy juan, que modelo sos?")

        logger.info(f"Respuesta: {respuesta}")
              
