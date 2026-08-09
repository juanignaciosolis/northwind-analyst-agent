import logging
from logging import Logger

logger: Logger = logging.getLogger(__name__)

from openai import OpenAI, AsyncOpenAI
import time
import asyncio
from typing import AsyncIterator


from .contract import GenerationResult
from src.utils.validators import temperature_validator,message_validator
from src.utils.decorators import retry_backoff
from src.prompts.user_prompt import prompt_constructor
from src.utils.tokenomics import auditar_tokenomics
from src.schemas.output_schemas import AnswerOpenAIScheme
from src.utils.errors import (ProviderConfigurationError,
                              RateLimitError, 
                              ProviderTimeoutError, 
                              TransientProviderError,
                              InvalidProviderResponseError,
                              InvalidRequestError)

class OpenAIClient:
    def __init__(self, api_key: str | None, model: str):

        logger.info("Se inicializa el cliente de OpenAI...")

        if not api_key:
            raise ProviderConfigurationError("Falta OPENAI_API_KEY")

        self.model = model
        self.client = OpenAI(api_key = api_key)
        self.aclient = AsyncOpenAI(api_key=api_key)

        logger.info("¡Éxito! Cliente instanciado")

    @staticmethod
    def _map_exception(exc: Exception) -> Exception:
        text = str(exc).lower()
        if "429" in text or "rate limit" in text or "resource exhausted" in text:
            return RateLimitError(str(exc))
        if "timeout" in text or "timed out" in text:
            return ProviderTimeoutError(str(exc))
        if "401" in text or "403" in text or "api key" in text:
            return ProviderConfigurationError(str(exc))
        return TransientProviderError(str(exc))

    @staticmethod
    def _usage(response) -> tuple[int, int]:
        usage = getattr(response, "usage", None)
        return (
            int(getattr(usage, "prompt_tokens", 0) or 0),
            int(getattr(usage, "completetion_tokens", 0) or 0),
        )

    def _normalize(self, response, started: float) -> GenerationResult:
        text = response.output_parsed or ""
        if not text:
            text = AnswerOpenAIScheme(
                type = "OpenAI_scheme",
                error="Fallback",
                resumen="El modelo genero una respuesta vacia",
                evidence=["respuesta vacia"],
                human_revision=True,
                confidence= 0.2
            )
            
        input_tokens, output_tokens = self._usage(response)
        return GenerationResult(
            text=text,
            model=self.model,
            provider="openai",
            latency=round((time.perf_counter() - started) * 1000, 2),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens= input_tokens + output_tokens
        )

    @auditar_tokenomics
    @retry_backoff(3,0.3)
    def generate(self, prompt: str, *, system: str | None = None, temperature: float = 0.2, max_output_tokens: int | None = None) -> GenerationResult:

        logger.debug(f"Configuracion:\nSystem Prompt - {"Contiene" if system else "No contiene"}\nTemperature - {temperature}\nMax. Output Tokens - {max_output_tokens}")

        logger.debug(f"[bold yellow]System prompt cargado:[/]\n{system}")

        mesagge = message_validator(prompt)
        prompt = prompt_constructor(mesagge)

        logger.debug("Prompt: " + f"[orange3]{prompt}[/]")

        try:
            started = time.perf_counter()
            response = self.client.responses.parse(
                model=self.model,
                instructions=system,
                store=False,
                input=prompt,
                temperature= temperature_validator(temperature),
                max_output_tokens=max_output_tokens,
                text_format=AnswerOpenAIScheme)

            logger.info("Llamada exitosa!")

            answer = self._normalize(response, started)

            return answer
        
        except Exception as exc:
            if isinstance(exc, InvalidProviderResponseError):
                raise
            raise self._map_exception(exc) from exc


    async def agenerate(self, prompt: str, *, system: str | None = None, temperature: float = 0.2) -> GenerationResult:
        if not prompt.strip():
            raise InvalidRequestError("El prompt no puede estar vacío")
        started = time.perf_counter()
        try:
            response = await self.aclient.responses.parse(
                model=self.model,
                instructions=system,
                store=False,
                input=prompt,
                temperature= temperature_validator(temperature),
                text_format=AnswerOpenAIScheme)
            
            return self._normalize(response, started)
        except Exception as exc:
            if isinstance(exc, InvalidProviderResponseError):
                raise
            raise self._map_exception(exc) from exc

    async def astream(self, prompt: str, *, system: str | None = None, temperature: float = 0.2) -> AsyncIterator[str]:
        if not prompt.strip():
            raise InvalidRequestError("El prompt no puede estar vacío")
        try:
            stream =  await self.aclient.responses.parse(
                model=self.model,
                instructions=system,
                store=False,
                input=prompt,
                temperature= temperature_validator(temperature),
                text_format=AnswerOpenAIScheme,
                stream= True)
            
            async for chunk in stream:
                text = chunk.delta or ""
                if text:
                    yield text
        except Exception as exc:
            raise self._map_exception(exc) from exc