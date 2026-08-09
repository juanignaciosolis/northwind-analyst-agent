import logging
from logging import Logger

logger: Logger = logging.getLogger(__name__)

import functools
import time
import os
import asyncio
from src.settings import settings
from dataclasses import dataclass, asdict
from typing import Callable, Any, Annotated, Union
from src.schemas.output_schemas import SQLAnswer, InvalidAnswerScheme, AnswerOpenAIScheme
from pydantic import ValidationError, TypeAdapter, Field
import json
from src.core.llm.contract import GenerationResult
from src.utils.errors import RETRYABLE_ERRORS, ProviderTimeoutError
import random

RespuestaUnion = Annotated[
    Union[SQLAnswer, InvalidAnswerScheme, AnswerOpenAIScheme],
    Field(discriminator='type')
]

answer_validator_router = TypeAdapter(RespuestaUnion)

SQL_SCHEMA_STR = json.dumps(SQLAnswer.model_json_schema(), ensure_ascii=False)
INV_SCHEMA_STR = json.dumps(InvalidAnswerScheme.model_json_schema(), ensure_ascii=False)


@dataclass(frozen=True)
class RetryEvent:
    attempt: int
    error_type: str
    message: str
    next_delay_seconds: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class CallOutcome:
    result: GenerationResult
    attempts: int
    retries: tuple[RetryEvent, ...]


def retry_log(event: RetryEvent, delay: int) -> None:
    logger.debug( event.to_dict())

    logger.warning(f"Intento {event.attempt} FRACASADO. Se esperan {delay} antes de reintentar")


def retry_backoff(max_retries: int, 
                  base_delay_seconds: int, 
                  jitter: bool = True,
                  on_retry: Callable[[RetryEvent], None] | None = retry_log) -> Callable:
    
    def decorator(func: Callable) -> Callable:

        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            retries: list[RetryEvent] = []
            for attempt in range(1, max_retries + 2):
                try:
                    result = func(*args, **kwargs)
                    return CallOutcome(result=result, attempts=attempt, retries=tuple(retries))
                except RETRYABLE_ERRORS as exc:
                    error = exc

                    if attempt > max_retries:
                        raise error

                    delay = base_delay_seconds * (2 ** (attempt - 1))
                    if jitter:
                        delay *= random.uniform(0.8, 1.2)

                    event = RetryEvent(
                            attempt=attempt,
                            error_type=type(error).__name__,
                            message=str(error),
                            next_delay_seconds=round(delay, 4),
                            )
                    retries.append(event)
                    if on_retry:
                        on_retry(event,delay)

                    time.sleep(delay)

            raise RuntimeError("Estado inalcanzable")

        return wrapper
    return decorator


def aretry_backoff(max_retries: int, 
                  base_delay_seconds: int, 
                  jitter: bool = True,
                  on_retry: Callable[[RetryEvent], None] | None = retry_log,
                  timeout_seconds: float = 20.0) -> Callable:
    
    def decorator(func: Callable) -> Callable:

        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            retries: list[RetryEvent] = []
            for attempt in range(1, max_retries + 2):
                try:
                    result = await asyncio.wait_for(func(*args, **kwargs), timeout= timeout_seconds)
                    return CallOutcome(result=result, attempts=attempt, retries=tuple(retries))
                
                except asyncio.TimeoutError:
                    error = ProviderTimeoutError(
                    f"La llamada superó {timeout_seconds:.2f} segundos"
                    )

                except RETRYABLE_ERRORS as exc:
                    error = exc

                    if attempt > max_retries:
                        raise error

                    delay = base_delay_seconds * (2 ** (attempt - 1))

                    if jitter:
                        delay *= random.uniform(0.8, 1.2)

                    event = RetryEvent(
                            attempt=attempt,
                            error_type=type(error).__name__,
                            message=str(error),
                            next_delay_seconds=round(delay, 4),
                            )
                    retries.append(event)
                    if on_retry:
                        on_retry(event,delay)

                    time.sleep(delay)

            raise RuntimeError("Estado inalcanzable")

        return wrapper
    return decorator






def retry_backoff(intentos: int, delay: int) -> Callable:
    
    def decorator(func: Callable) -> Callable:

        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:

            resultado = None

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
                            f"Tu respuesta anterior no respetó la estructura obligatoria. Error: {schema_error}\n"
                            "Los esquemas de respuesta permitidos son:\n"
                            "## RESPUESTA con 'sql_success':\n" 
                            f"{SQL_SCHEMA_STR}\n"
                            "## RESPUESTA con 'invalid_query':\n"
                            f"{INV_SCHEMA_STR   }\n"
                            "Generá una nueva respuesta distinta analizando de nuevo todo el contexto provisto")
                        kwargs["prompt"] = prompt_modificado

                    resultado = func(*args, **kwargs)

                    if isinstance(resultado.text, (SQLAnswer, InvalidAnswerScheme, AnswerOpenAIScheme)):
                            respuesta = resultado.text
                    else:
                            respuesta = answer_validator_router.validate_json(resultado.text)

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

            return GenerationResult(
            text=None, 
            provider=settings.default_provider, 
            model=settings.gemini_default_model or settings.openai_default_model,
            latency= getattr(resultado,"latency",0) if resultado is not None else 0, 
            input_tokens=getattr(resultado,"input_tokens",0) if resultado is not None else 0, 
            output_tokens=getattr(resultado,"output_tokens",0) if resultado is not None else 0, 
            total_tokens=getattr(resultado,"total_tokens",0) if resultado is not None else 0
        )
        
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


    

                    

            

