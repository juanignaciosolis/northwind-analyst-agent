from logging import Logger
from src.utils.logger import setup_logger

logger: Logger = setup_logger(name=__name__)


from dotenv import load_dotenv
from pathlib import Path
import os

load_dotenv()

from src.core.llm import get_llm_client
from src.utils.database import execute_query, clean_sql_query
from src.utils.tokenomics import generar_reporte_markdown

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
        respuesta = client.send_message(prompt="Dame el monto de ventas totales por dia junto con el promedio movil con una ventana de 3 dias centralizada")

        logger.info(f"Respuesta: {respuesta}")

        generar_reporte_markdown()

        consulta = clean_sql_query(respuesta.text)

        logger.info(f"Consulta generada por el modelo:\n[bold yellow]{consulta}[/]")

        resultado = execute_query(consulta)

        logger.info(resultado)

        logger.info("Fin de la prueba")


              
