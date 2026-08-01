import logging
from src.utils.logger import setup_logger

setup_logger(console_level= logging.WARNING)

from dotenv import load_dotenv
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box
import json
from typing import Optional, Any
from dataclasses import dataclass
import pandas as pd

from src.core.llm import get_llm_client
from src.utils.database import  DatabaseManager, clean_sql_query
from src.prompts.system_prompt import zero_shot_system_prompt, few_shot_system_prompt
from src.utils.helpers import format_sql_query
from tests.eval_tool import equal_dataframes
from src.utils.helpers import generate_rich_table

logger = logging.getLogger(__name__)

load_dotenv()

TESTS_DIR = Path(__file__).resolve().parent

@dataclass
class EvaluationRecord:
    pregunta: str
    respuesta_esperada: str
    respuesta: Optional[Any] 
    acierto: bool
    latencia: float
    tokens_input: int
    thinking: int
    outputs: int
    total_tokens: int


with open(TESTS_DIR / "eval_dataset.json", "r", encoding="utf-8") as archivo:
    datos = json.load(archivo)

console = Console()

system_prompt_content = zero_shot_system_prompt()

console.print("[bold yellow]=[/]"*35,"[bold yellow]INICIO DE TEST[/]","[bold yellow]=[/]"*35,"\n\n")

console.print("[bold yellow]Elija sistem prompt...[/]", end=" ")
system = input()

if system.upper() == "ZERO":
    system_prompt_content = zero_shot_system_prompt()
else:
    system_prompt_content = few_shot_system_prompt()

client = get_llm_client(system_prompt = system_prompt_content)

resultados = []

with DatabaseManager() as db:

    for numero,test in enumerate(datos[:2],1):

        console.rule(f"[bold blue]\nMENSAJE {numero} DE {len(datos)}[/]",style="blue",characters="*")

        pregunta = test["question"]

        console.print(f"[bold yellow]Pregunta: {pregunta}[/]\n")

        respuesta = client.send_message(pregunta)

        df_python = json.loads(test["result"])
        df_esperado = pd.DataFrame(df_python)

        if respuesta.text is None:

            resultado = EvaluationRecord(
                pregunta= pregunta,
                respuesta_esperada= test["query"],
                respuesta= None,
                acierto= False,
                latencia= respuesta.latency,
                tokens_input= respuesta.input_tokens,
                thinking= respuesta.thinking_tokens,
                outputs= respuesta.output_tokens,
                total_tokens= respuesta.total_tokens
            )
        else:
            respuesta_curada = clean_sql_query(respuesta.text.query)

            df = db.execute(respuesta_curada, limit= 10)

            acierto = equal_dataframes(df, df_esperado)

            resultado = EvaluationRecord(
                    pregunta= pregunta,
                    respuesta_esperada= test["query"],
                    respuesta= respuesta.text.query,
                    acierto= acierto,
                    latencia= respuesta.latency,
                    tokens_input= respuesta.input_tokens,
                    thinking= respuesta.thinking_tokens,
                    outputs= respuesta.output_tokens,
                    total_tokens= respuesta.total_tokens
                )
        
        resultados.append(resultado)

        sql_esperado = format_sql_query(test["query"])

        sql_real = format_sql_query(respuesta.text.query) if resultado.respuesta else "[bold red]⚠ No se pudo obtener una respuesta válida[/bold red]"

        tabla = Table(show_header=True, header_style="bold white", box=None, expand=True)
        tabla.add_column("Consulta Esperada", justify="left")
        tabla.add_column("Consulta Generada", justify="left")

        # 4. Agregar la fila
        tabla.add_row(sql_esperado,sql_real)

        # 5. Imprimir Panel
        console.print(
            Panel(
                tabla,
                title="[bold white]Comparativa Consultas SQL[/]",
                border_style="cyan",
                box=box.HEAVY,
                padding=(1, 1)
            )
        )

        df_esperado = generate_rich_table(df_esperado)

        df_real = generate_rich_table(df) if resultado.respuesta else "[bold red]⚠ No se pudo obtener una respuesta válida[/bold red]"

        if resultado.acierto:
            console.print("[bold green][ACIERTO] EL AGENTE RESPONDIO CORRECTAMENTE[/]\n")
        else:
            console.print("[bold red][FALLO] EL AGENTE NO RESPONDIO CORRECTAMENTE[/]\n")


        tabla = Table(show_header=True, header_style="bold white", box=None, expand=True)
        tabla.add_column("Resultado Esperado", justify="left")
        tabla.add_column("Resultado Generado", justify="left")

        # 4. Agregar la fila
        tabla.add_row(df_esperado, df_real)

        # 5. Imprimir Panel
        console.print(
            Panel(
                tabla,
                title="[bold white]Comparativa DataFrames[/]",
                border_style="dark_orange3",
                box=box.HEAVY,
                padding=(1, 1)
            )
        )

    stop = input()
    console.print("[bold violet]Aprete enter para FINALIZAR y generar reporte...[/]", end="\n")

    print(resultados)

    

