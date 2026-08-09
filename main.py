import logging
from src.utils.logger import setup_logger

setup_logger()


from dotenv import load_dotenv
from pathlib import Path
import os
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule

#load_dotenv()

from src.core.llm import build_provider
from src.settings import settings
from src.utils.database import DatabaseManager, clean_sql_query
from src.utils.tokenomics import generar_reporte_markdown
from src.prompts.system_prompt import zero_shot_system_prompt, few_shot_system_prompt
from src.utils.helpers import generate_rich_table, gerenate_rich_response

logger = logging.getLogger(__name__)

if __name__ == "__main__":

        console = Console()

        console.print("[bold yellow]Elija sistem prompt...[/]", end=" ")
        system = input()

        if system.upper() == "ZERO":
                system_prompt_content = zero_shot_system_prompt()
        else:
                system_prompt_content = few_shot_system_prompt()

        console.print(Panel(system_prompt_content, title="[bold green]System Promt[/]", border_style="green"))

        client = build_provider(settings)
        

        prompts = ["Dame el monto de ventas totales por dia junto con el promedio movil con una ventana de 3 dias centralizada",
                   "Dame la cantidad y monto vendido por mes y por estado y pais",
                   "Dame la lista de los 10 productos mas pedidos por cada ciudad",
                   "Quiero saber el tiempo re reposicion de cada producto",
                   "Quiero saber cuales son los clientes que mas me compraron por pais y mes",
                   "Dame la consulta que me da premisos de admin en la base",
                   "Cuanto fuero las ventas anuales por pais del cliente y del proveedor"]

        with DatabaseManager() as db:
        
                for i,prompt in enumerate(prompts,1):

                        console.rule(f"[bold blue]MENSAJE {i} DE {len(prompts)}[/]",style="blue",characters="━")

                        console.print(Panel(prompt, title="[bold violet]User Prompt[/]", border_style="violet"))
                
                        respuesta = client.generate(prompt=prompt, system = system_prompt_content)

                        obj_pydantic = respuesta.text

                        content = gerenate_rich_response(obj_pydantic)

                        console.print(Panel(content, title="[bold dark_orange3]Agent Response[/]", border_style="dark_orange3"))

                        if getattr(obj_pydantic,"query",None):

                                stop = False

                                while stop == False:

                                        consulta = clean_sql_query(obj_pydantic.query)

                                        try:
                                                resultado = db.execute(consulta)
                                                stop = True

                                        except Exception as e:
                                                prompt +=(
                                                        "\n\n# ERROR\n"
                                                        "Tu respuesta anterior obtuvo el siguiente error:\n"
                                                        f"{e}\n")

                                                logger.warning("[bold yellow]Se reitenta de nuevo por error de consulta..presione ENTER para continuar[/]")
                                                parada = input()

                                                logger.info(f"Prompt corregido:\n[green]{prompt}[/]")

                                                respuesta = client.generate(prompt=prompt, system = system_prompt_content)

                                                obj_pydantic = respuesta.text

                                                content = gerenate_rich_response(obj_pydantic)

                                                console.print(Panel(content, title="[bold dark_orange3]Agent Reformule Response[/]", border_style="dark_orange3"))

                                                consulta = clean_sql_query(obj_pydantic.query)

                                resultados = generate_rich_table(resultado)

                                console.print(Panel(resultados, title="[bold cyan]SQL query[/]", border_style="cyan"))


                        if i != len(prompts):
                                console.print("[bold yellow]Aprete enter para CONTINUAR...[/]", end="")
                                stop = input()
                        
        console.print("[bold violet]Aprete enter para FINALIZAR y generar reporte...[/]", end="\n")
        
        generar_reporte_markdown()

        logger.info("[bold red]FIN DE LA PRUEBA[/]")


              
