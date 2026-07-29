import logging

logger = logging.getLogger("agent_logger.tokenomics")

import functools
import time
from typing import Callable, Any, Annotated, Union
import requests
from src.schemas.output_schemas import SQLAnswer, InvalidAnswerScheme, AnswerOpenAIScheme
from pydantic import ValidationError, TypeAdapter, Field
import json

RespuestaUnion = Annotated[
    Union[SQLAnswer, InvalidAnswerScheme, AnswerOpenAIScheme],
    Field(discriminator='type')
]

answer_validator_router = TypeAdapter(RespuestaUnion)

SQL_SCHEMA_STR = json.dumps(SQLAnswer.model_json_schema(), ensure_ascii=False)
INV_SCHEMA_STR = json.dumps(InvalidAnswerScheme.model_json_schema(), ensure_ascii=False)

def retry_backoff(intentos: int, delay: int) -> Callable:
    
    def decorator(func: Callable) -> Callable:

        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:

            prompt_base = kwargs.get("prompt","")

            schema_error = None

            max_intentos = intentos
            intento = 1

            logger.info("Realizando llamada..")

            while intento <= max_intentos:

                try:
                    if schema_error:
                        prompt_modificado = prompt_base + (
                            "\n\n# ERROR\n"
                            "Tu respuesta anterior no respetó la estructura obligatoria. Los esquemas de respuesta permitidos son\n"
                            "## RESPUESTA con 'sql_success':\n" 
                            f"{SQL_SCHEMA_STR}\n"
                            "## RESPUESTA con 'invalid_query':\n"
                            f"{INV_SCHEMA_STR   }")
                        kwargs["prompt"] = prompt_modificado

                    resultado = func(*args, **kwargs)

                    if isinstance(resultado.text, (SQLAnswer, InvalidAnswerScheme, AnswerOpenAIScheme)):
                            respuesta = resultado.text
                    else:
                            respuesta = answer_validator_router.validate_python(resultado.text)

                    if isinstance(respuesta, SQLAnswer):                 
                        logger.info(f"Llama exitosa en {intento} intentos. Consulta SQL devuelta")
                    else:
                        logger.info(f"Llama exitosa en {intento} intentos. Error reportado")
                    return resultado
                except ValidationError as e:
                    logger.error(f"[bold yellow]Llamada fallida: {e}, intento {intento}, se vuelve a intentar...[/]")
                    potencia = delay ** intento
                    if intento == max_intentos:
                        break
                    intento += 1
                    schema_error = e
                    logger.warning(f"[bold yellow]Se esperan {potencia} segundos antes de reintentar[/]")
                    time.sleep(potencia)

                except Exception as e:
                    logger.error(f"[bold yellow]Llamada fallida: {e}, intento {intento}, se vuelve a intentar...[/]")
                    potencia = delay ** intento
                    if intento == max_intentos:
                        break
                    intento += 1
                    logger.warning(f"[bold yellow]Se esperan {potencia} segundos antes de reintentar[/]")
                    time.sleep(potencia)
            
            logger.error(f"[bold red]Se acabaron todos lo intentos. En total {max_intentos}[/]")
            #raise Exception("Máximo de intentos fallidos en la API.")
        
        return wrapper
    return decorator
          


if __name__ == "__main__":

    # Simulación A: Una función que devuelve un JSON válido de SQL
    @retry_backoff(intentos=2, delay=1)
    def funcion_simulada_exitosa(prompt: str):
        return json.dumps({
            "type": "sql_success",
            "query": "SELECT * FROM users;",
            "human_revision": False,
            "confidence": 0.95
        })

    # Simulación B: Una función que falla en el primer intento y se corrige en el segundo
    contador_intentos = 0

    @retry_backoff(intentos=2, delay=1)
    def funcion_simulada_con_correccion(prompt: str):
        global contador_intentos
        contador_intentos += 1
        
        # En el primer intento devuelve un JSON inválido (le falta el campo 'query')
        if contador_intentos == 1:
            logger.info(f"\n--- PROMPT RECIBIDO (Intento 1) ---\n{prompt}")
            return json.dumps({"type": "sql_success", "confidence": 0.5}) 
        
        # En el segundo intento (tras recibir la corrección en el prompt) responde bien
        logger.info(f"\n--- PROMPT RECIBIDO (Intento 2 con Feedback) ---\n{prompt}")
        return json.dumps({
            "type": "sql_success", 
            "query": "SELECT COUNT(*) FROM ventas;",
            "human_revision": False,
            "confidence": 0.99
        })

    # Ejecución de pruebas
    logger.info("=== PRUEBA 1: Respuesta exitosa directa ===")
    res1 = funcion_simulada_exitosa(prompt="¿Cuántos usuarios hay?")
    logger.info(f"Resultado instanciado: {type(res1)} -> {res1.query}\n")

    logger.info("=== PRUEBA 2: Reintento con auto-corrección de Prompt ===")
    res2 = funcion_simulada_con_correccion(prompt="Dame las ventas")
    logger.info(f"Resultado instanciado: {type(res2)} -> {res2.query}")

    logger.info("Prueba terminada")


    

                    

            

