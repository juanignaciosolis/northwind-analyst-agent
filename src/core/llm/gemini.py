import logging
from logging import Logger

logger: Logger = logging.getLogger(__name__)

from google import genai
from google.genai import types
from typing import Optional
import os
import time
import asyncio
from typing import AsyncIterator


from .contract import GenerationResult
from src.utils.decorators import retry_backoff
from src.utils.validators import temperature_validator,message_validator
from src.prompts.user_prompt import prompt_constructor
from src.utils.tokenomics import auditar_tokenomics
from src.schemas.output_schemas import SQLAnswer, InvalidAnswerScheme
from src.utils.errors import EmptyRespondError
from src.utils.errors import (ProviderConfigurationError,
                              RateLimitError, 
                              ProviderTimeoutError, 
                              TransientProviderError,
                              InvalidProviderResponseError,
                              InvalidRequestError)


class GeminiClient:

    def __init__(self, api_key: str | None, model: str):

        logger.info("Se inicializa el cliente de Gemini...")

        if not api_key:
            raise ProviderConfigurationError("Falta GEMINI_API_KEY")

        self.model = model
        self.client = genai.Client(api_key=api_key)

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
    def _config(system: str | None, temperature: float, max_output_tokens: int | None):

        return types.GenerateContentConfig(
            system_instruction=system,
            temperature=temperature_validator(temperature),
            max_output_tokens = max_output_tokens,
            response_schema=SQLAnswer | InvalidAnswerScheme 
        )

    @staticmethod
    def _usage(response) -> tuple[int, int]:
        usage = getattr(response, "usage_metadata", None)
        return (
            int(getattr(usage, "prompt_token_count", 0) or 0),
            int(getattr(usage, "candidates_token_count", 0) or 0),
        )

    def _normalize(self, response, started: float) -> GenerationResult:
        text = response.parsed or ""
        if not text:
            raise InvalidProviderResponseError("Gemini devolvió texto vacío")
        input_tokens, output_tokens = self._usage(response)
        return GenerationResult(
            text=text,
            model=self.model,
            provider="gemini",
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

        logger.debug("Prompt del usuario: " + f"[orange3]{prompt}[/]")

        logger.info("Se evia el mensaje por API")

        started = time.perf_counter()
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=self._config(system, temperature, max_output_tokens),
            )

            answer = self._normalize(response, started)

            logger.info("Llamada exitosa!")

            logger.debug(f"Respuesta generada por el modelo:\n[bold yellow]{response.parsed.model_dump_json(indent=4)}[/]")

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
            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=prompt,
                config=self._config(system, temperature),
            )
            return self._normalize(response, started)
        except Exception as exc:
            if isinstance(exc, InvalidProviderResponseError):
                raise
            raise self._map_exception(exc) from exc

    async def astream(self, prompt: str, *, system: str | None = None, temperature: float = 0.2) -> AsyncIterator[str]:
        if not prompt.strip():
            raise InvalidRequestError("El prompt no puede estar vacío")
        try:
            stream = await self.client.aio.models.generate_content_stream(
                model=self.model,
                contents=prompt,
                config=self._config(system, temperature),
            )
            async for chunk in stream:
                text = chunk.text or ""
                if text:
                    yield text
        except Exception as exc:
            raise self._map_exception(exc) from exc

