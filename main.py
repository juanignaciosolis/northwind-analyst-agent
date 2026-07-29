from logging import Logger
from src.utils.logger import setup_logger

logger: Logger = setup_logger(name=__name__)


from dotenv import load_dotenv
from pathlib import Path
import os
from rich.console import Console

load_dotenv()

from src.core.llm import get_llm_client
from src.utils.database import execute_query, clean_sql_query
from src.utils.tokenomics import generar_reporte_markdown
from src.prompts.system_prompt import zero_shot_system_prompt, few_shot_system_prompt

if __name__ == "__main__":



        system_prompt_content = few_shot_system_prompt()
        logger.info(f"[bold yellow]System prompt cargado con éxito:[/]\n{system_prompt_content}")


        client = get_llm_client(system_prompt = system_prompt_content)
        logger.info("¡Éxito! Cliente instanciado")

        prompts = ["Dame el monto de ventas totales por dia junto con el promedio movil con una ventana de 3 dias centralizada",
                   "Dame la cantidad y monto vendido por mes y por estado y pais",
                   "Dame la lista de los 10 productos mas pedidos por cada ciudad",
                   "Quiero saber el tiempo re reposicion de cada producto",
                   "Quiero saber cuales son los clientes que mas me compraron por pais y mes",
                   "Dame la consulta que me da premisos de admin en la base"]
        
        for i,prompt in enumerate(prompts,1):

                logger.info("="*54 + f"\nMENSAJE {i} DE {len(prompts)}\n" + "="*54)

                logger.info("\nEnviando mensaje de prueba...")
                
                respuesta = client.send_message(prompt=prompt)

                obj_pydantic = respuesta.text

                logger.info(f"Respuesta generada por el modelo:\n[bold yellow]{obj_pydantic.model_dump_json(indent=4)}[/]")


                if obj_pydantic.type == "sql_success":

                        consulta = clean_sql_query(obj_pydantic.query)

                        resultado = execute_query(consulta)

                        logger.info(resultado)

                console = Console()

                if i != len(prompts):
                        console.print("[bold yellow]Aprete enter para CONTINUAR...[/]", end="")
                        stop = input()
                        
        console.print("[bold violet]Aprete enter para FINALIZAR y generar reporte...[/]", end="\n")
        
        generar_reporte_markdown()

        logger.info("[bold red]FIN DE LA PRUEBA[/]")


              
