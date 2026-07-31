import logging
from logging import Logger
from src.utils.logger import setup_logger

setup_logger(console_level= logging.WARNING)

from dotenv import load_dotenv
from pathlib import Path
import os
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box
import json
from typing import Optional, Any
from dataclasses import dataclass

from src.core.llm import get_llm_client
from src.utils.database import  DatabaseManager, clean_sql_query
from src.prompts.system_prompt import zero_shot_system_prompt, few_shot_system_prompt
from src.utils.helpers import format_sql_query

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

client = get_llm_client(system_prompt = system_prompt_content)

resultados = []

for numero,test in enumerate(datos,1):

    console.rule(f"[bold blue]MENSAJE {numero} DE {len(datos)}[/]",style="blue",characters="*")

    pregunta = test["question"]

    console.print(f"[bold yellow]Pregunta: {pregunta}[/]\n")

    respuesta = client.send_message(pregunta)

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
        evidencias_lower = [e.lower() for e in test["evidence"]]
        if any(evidencia in  respuesta.text.query.lower() for evidencia in evidencias_lower):
            acierto = True
        else:
            acierto = False

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

    sql_real = format_sql_query(resultado.respuesta) if resultado.respuesta else "[bold red]⚠ No se pudo obtener una respuesta válida[/bold red]"

    console.print(f"[bold]Evidencias buscadas: {test["evidence"]}[/]\n")

    if acierto:
        console.print("[bold green][ACIERTO] EL AGENTE RESPONDIO CORRECTAMENTE[/]\n")
    else:
        console.print("[bold red][FALLO] EL AGENTE NO RESPONDIO CORRECTAMENTE[/]\n")


    tabla = Table(show_header=True, header_style="bold white", box=None, expand=True)
    tabla.add_column("SQL Esperado", justify="left")
    tabla.add_column("SQL Generado", justify="left")

    # 4. Agregar la fila
    tabla.add_row(sql_esperado, sql_real)

    # 5. Imprimir Panel
    console.print(
        Panel(
            tabla,
            title="[bold white]Comparativa SQL[/]",
            border_style="dark_orange3",
            box=box.HEAVY,
            padding=(1, 1)
        )
    )

    console.print("[bold violet]Aprete enter para CONTINUAR con la siguiente pregunta...[/]", end="\n")

    stop = input()

    

