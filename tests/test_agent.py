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
from datetime import datetime
import os

from src.core.llm import build_provider
from src.settings import settings
from src.utils.database import  DatabaseManager, clean_sql_query
from src.prompts.system_prompt import zero_shot_system_prompt, few_shot_system_prompt
from src.utils.helpers import format_sql_query
from tests.eval_tool import equal_dataframes
from src.utils.helpers import generate_rich_table, imprimir_tabla_evaluacion
from tests.evaluation_history import registrar_evaluacion
from src.schemas.output_schemas import SQLAnswer, InvalidAnswerScheme, AnswerOpenAIScheme

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
    tokens_outputs: int
    total_tokens: int


with open(TESTS_DIR / "eval_dataset.json", "r", encoding="utf-8") as archivo:
    datos = json.load(archivo)

console = Console()

console.rule("[bold yellow]INICIO DE TEST[/]",style="yellow",characters="=")

console.print("[bold yellow]Elija sistem prompt...[/]", end=" ")
system = input()

if system.upper() == "ZERO":
    system_prompt_content = zero_shot_system_prompt()
else:
    system_prompt_content = few_shot_system_prompt()

console.print("[bold yellow]System prompt...[/]")
console.print(system_prompt_content)
    
client = build_provider(settings)

resultados = []

with DatabaseManager() as db:

    for numero,test in enumerate(datos,1):

        console.rule(f"[bold blue]\nMENSAJE {numero} DE {len(datos)}[/]",style="blue",characters="*")

        pregunta = test["question"]

        console.print(f"[bold yellow]Pregunta: {pregunta}[/]\n")

        respuesta = client.generate(prompt=pregunta, system = system_prompt_content)

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
                tokens_outputs= respuesta.output_tokens,
                total_tokens= respuesta.total_tokens
            )

        elif getattr(respuesta.text,"query",None) is None:

            resultado = EvaluationRecord(
                pregunta= pregunta,
                respuesta_esperada= test["query"],
                respuesta= None,
                acierto= False,
                latencia= respuesta.latency,
                tokens_input= respuesta.input_tokens,
                tokens_outputs= respuesta.output_tokens,
                total_tokens= respuesta.total_tokens
            )           

        else:
            respuesta_curada = clean_sql_query(respuesta.text.query)

            for i in range(3):

                try:
                    
                    df = db.execute(respuesta_curada, limit= 10)

                    break

                except Exception as e:
                    logger.error(f"Se produjo el siguiente error al ejecutar la query: {e}. Se intenta de nuevo")

                    pregunta +=("\n\n# ERROR\n"
                            "Tu respuesta anterior obtuvo el siguiente error:\n"
                            f"{e}\n")
                    respuesta = client.generate(prompt=pregunta, system = system_prompt_content)

                    respuesta_curada = clean_sql_query(respuesta.text.query)


            acierto = equal_dataframes(df, df_esperado)

            resultado = EvaluationRecord(
                    pregunta= pregunta,
                    respuesta_esperada= test["query"],
                    respuesta= respuesta.text.query,
                    acierto= acierto,
                    latencia= respuesta.latency,
                    tokens_input= respuesta.input_tokens,
                    tokens_outputs= respuesta.output_tokens,
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

console.rule("[bold violet]Aprete enter para FINALIZAR y generar reporte...[/]",style="violet   ",characters="=")
stop = input()

fecha =  datetime.now().strftime("%Y-%m-%d %H:%M")
proveedor = settings.default_provider
modelo = settings.gemini_default_model if proveedor == "GEMINI" else settings.openai_default_model
system_prompt = "ZERO SHOTS" if system.upper() == "ZERO" else "FEW SHOTS"
latencia_promedio = sum(resultado.latencia for resultado in resultados) / len(resultados)
casos = len(resultados)
aciertos = sum(resultado.acierto for resultado in resultados)
sin_respuesta = sum(1 for resultado in resultados if resultado.respuesta is None)
mal_formadas = casos - aciertos - sin_respuesta
precision = aciertos / casos
p_sin_respuesta = sin_respuesta / casos
p_mal_formadas = mal_formadas / casos

resumen = {
    "fecha": fecha,
    "provedor": proveedor,
    "modelo": modelo,
    "system_promt": system_prompt,
    "latencia_promedio": latencia_promedio,
    "casos": casos,
    "aciertos": aciertos,
    "sin_respuesta": sin_respuesta,
    "mal_formadas": mal_formadas,
    "precision": precision,
    "p_sin_respuesta": p_sin_respuesta,
    "p_mal_formadas": p_mal_formadas
}

imprimir_tabla_evaluacion(resumen)

logger.debug(f"Se corre una evalaucion del agente con los siguientes resultados: {resumen}")

registrar_evaluacion(resumen)

    

