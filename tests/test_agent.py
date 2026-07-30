import logging
from logging import Logger
from src.utils.logger import setup_logger

logger: Logger = setup_logger(name=__name__, console_level=logging.WARNING)

from dotenv import load_dotenv
from pathlib import Path
import os
from rich.console import Console
import json

from src.core.llm import get_llm_client
from src.utils.database import execute_query, clean_sql_query
from src.prompts.system_prompt import zero_shot_system_prompt, few_shot_system_prompt

load_dotenv()

TESTS_DIR = Path(__file__).resolve().parent


with open(TESTS_DIR / "eval_dataset.json", "r", encoding="utf-8") as archivo:
    datos = json.load(archivo)

console = Console()

system_prompt_content = zero_shot_system_prompt()

console.print("[bold yellow]=[/]"*35,"[bold yellow]INICIO DE TEST[/]","[bold yellow]=[/]"*35)

client = get_llm_client(system_prompt = system_prompt_content)

for numero,test in enumerate(datos,1):


    console.print("[bold blue]*[/]"*35,f"[bold blue]PREGUNTA N. {numero}[/]","[bold blue]*[/]"*35)


    pregunta = test["question"]

    respuesta = client.send_message(pregunta)

    sql = respuesta.text

    console.print(sql)

    console.print("[bold violet]Aprete enter para CONTINUAR con la siguiente pregunta...[/]", end="\n")

    stop = input()

    

