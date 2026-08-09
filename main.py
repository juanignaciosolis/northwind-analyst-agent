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
from typing import Annotated, Union
from src.schemas.output_schemas import SQLAnswer, InvalidAnswerScheme, AnswerOpenAIScheme
from psycopg2 import  ProgrammingError, DataError
from pydantic import ValidationError, TypeAdapter, Field
import json
import time
from src.utils.errors import InvalidProviderResponseError

logger = logging.getLogger(__name__)

RespuestaUnion = Annotated[
    Union[SQLAnswer, InvalidAnswerScheme, AnswerOpenAIScheme],
    Field(discriminator='type')
]

answer_validator_router = TypeAdapter(RespuestaUnion)

SQL_SCHEMA_STR = json.dumps(SQLAnswer.model_json_schema(), ensure_ascii=False)
INV_SCHEMA_STR = json.dumps(InvalidAnswerScheme.model_json_schema(), ensure_ascii=False)

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

                        intentos = 0

                        original = prompt

                        for attemp in range(0,3):

                                try:
                                        respuesta = client.generate(prompt=prompt, system = system_prompt_content)

                                        content = respuesta.text

                                        answer_validator_router.validate_python(content)

                                        resultado = content

                                        if getattr(content,"query",None):

                                                consulta = clean_sql_query(content.query)

                                                resultado = db.execute(consulta)

                                        break

                                except ValidationError as e:
                                        logger.error(f"[bold red]Llamada fallida: {e}, intento {attemp}, se vuelve a intentar...[/]")
                                        potencia = 0.3 ** attemp
                                        logger.warning(f"[bold yellow]Se esperan {potencia} segundos antes de reintentar[/]")
                                        prompt = original + (
                                                                "\n\n# ERROR\n"
                                                                f"Tu respuesta anterior no respetó la estructura obligatoria. Error: {e}\n"
                                                                "Los esquemas de respuesta permitidos son:\n"
                                                                "## RESPUESTA con 'sql_success':\n" 
                                                                f"{SQL_SCHEMA_STR}\n"
                                                                    "## RESPUESTA con 'invalid_query':\n"
                                                                f"{INV_SCHEMA_STR   }\n"
                                                                "Generá una nueva respuesta distinta analizando de nuevo todo el contexto provisto")
                                        intentos += 1

                                        time.sleep(potencia)

                                except InvalidProviderResponseError as e:
                                        logger.error(f"[bold red]{e}. Se vuelve a reintentar[/]")

                                        intentos += 1

                                except (ProgrammingError, DataError) as e:
                                                prompt = original + (
                                                        "\n\n# ERROR\n"
                                                        "Tu respuesta anterior obtuvo el siguiente error:\n"
                                                        f"{e}\n")

                                                logger.warning("[bold yellow]Se reitenta de nuevo por error de consulta..presione ENTER para continuar[/]")
                                                parada = input()

                                                logger.info(f"Prompt corregido:\n[green]{prompt}[/]")

                                                intentos += 1

                                except Exception as e:

                                        logger.error(f"[bold red]Llamada fallida: {e}[/]")

                                        intentos += 1

                        if intentos == 3:

                                logger.error(f"[bold red]Se alcanzo el maximo de intentos 3[/]")

                                resultado = None

                                content = InvalidAnswerScheme(type="invalid_query",
                                                              error="Fallback",
                                                              resumen="Respuesta vacia del modelo",
                                                              evidence= ["Vacia"],
                                                              confidence= 0)


                        content = gerenate_rich_response(content)

                        console.print(Panel(content, title="[bold dark_orange3]Agent Response[/]", border_style="dark_orange3"))

                        resultados = generate_rich_table(resultado)
                        
                        console.print(Panel(resultados, title="[bold cyan]SQL query[/]", border_style="cyan"))

                        console.print("[bold yellow]Aprete enter para CONTINUAR...[/]", end="")

                        stop = input()
                        
        console.print("[bold violet]Aprete enter para FINALIZAR y generar reporte...[/]", end="\n")
        
        generar_reporte_markdown()

        logger.info("[bold red]FIN DE LA PRUEBA[/]")


              
