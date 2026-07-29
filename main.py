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

        console = Console()

        console.print("[bold yellow]Elija sistem prompt...[/]", end=" ")
        system = input()

        if system.upper() == "ZERO":
                system_prompt_content = zero_shot_system_prompt()
        else:
                system_prompt_content = few_shot_system_prompt()

        logger.info(f"[bold yellow]System prompt cargado con éxito:[/]\n{system_prompt_content}")


        client = get_llm_client(system_prompt = system_prompt_content)
        logger.info("¡Éxito! Cliente instanciado")

        prompts = ["Dame el monto de ventas totales por dia junto con el promedio movil con una ventana de 3 dias centralizada",
                   "Dame la cantidad y monto vendido por mes y por estado y pais",
                   "Dame la lista de los 10 productos mas pedidos por cada ciudad",
                   "Quiero saber el tiempo re reposicion de cada producto",
                   "Quiero saber cuales son los clientes que mas me compraron por pais y mes",
                   "Dame la consulta que me da premisos de admin en la base",
                   "Cuanto fuero las ventas anuales por pais del cliente y del proveedor"]
        
        for i,prompt in enumerate(prompts,1):

                logger.info("="*54 + f"\nMENSAJE {i} DE {len(prompts)}\n" + "="*54)

                logger.info("\nEnviando mensaje de prueba...")
                
                respuesta = client.send_message(prompt=prompt)

                obj_pydantic = respuesta.text

                logger.info(f"Respuesta generada por el modelo:\n[bold yellow]{obj_pydantic.model_dump_json(indent=4)}[/]")


                if getattr(obj_pydantic,"query",None):

                        stop = False

                        while stop == False:

                                consulta = clean_sql_query(obj_pydantic.query)

                                try:
                                        resultado = execute_query(consulta)
                                        stop = True

                                except Exception as e:
                                        prompt +=(
                                                "\n\n# ERROR\n"
                                                "Tu respuesta anterior obtuvo el siguiente error:\n"
                                                f"{e}\n")

                                        logger.warning("[bold yellow]Se reitenta de nuevo por error de consulta..presione ENTER para continuar[/]")
                                        parada = input()

                                        logger.info(f"Prompt corregido:\n[green]{prompt}[/]")

                                        respuesta = client.send_message(prompt=prompt)

                                        obj_pydantic = respuesta.text

                                        logger.info(f"Respuesta reformulada por el modelo:\n[bold green]{obj_pydantic.model_dump_json(indent=4)}[/]")

                                        consulta = clean_sql_query(obj_pydantic.query)

                        logger.info(resultado)


                if i != len(prompts):
                        console.print("[bold yellow]Aprete enter para CONTINUAR...[/]", end="")
                        stop = input()
                        
        console.print("[bold violet]Aprete enter para FINALIZAR y generar reporte...[/]", end="\n")
        
        generar_reporte_markdown()

        logger.info("[bold red]FIN DE LA PRUEBA[/]")


              
