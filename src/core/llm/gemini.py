import logging
from logging import Logger

logger: Logger = logging.getLogger(__name__)

from google import genai
from google.genai import types
from typing import Optional
import os
from time import perf_counter


from .base import LLMCliente, LLMResponse
from src.utils.validators import temperature_validator
from src.prompts.user_prompt import prompt_constructor
from src.utils.decorators import retry_backoff
from src.utils.tokenomics import auditar_tokenomics
from src.schemas.output_schemas import SQLAnswer, InvalidAnswerScheme
from src.utils.errors import EmptyRespondError
from src.settings import settings


class GeminiClient(LLMCliente):
    def __init__(self, system_prompt : Optional[str] = None, temperature: float = 0.2, max_output_tokens: int = None):

        logger.info("Se inicializa el cliente de Gemini...")

        logger.debug(f"Configuracion:\nSystem Prompt - {"Contiene" if system_prompt else "No contiene"}\nTemperature - {temperature}\nMax. Output Tokens - {max_output_tokens}")

        logger.debug(f"[bold yellow]System prompt cargado:[/]\n{system_prompt}")

        super().__init__(system_prompt, 
                         temperature,
                         max_output_tokens)

        self._client = genai.Client(api_key=settings.api_key_value())

        logger.info("¡Éxito! Cliente instanciado")

    @auditar_tokenomics
    @retry_backoff(3,2)
    def send_message(self, prompt: str, id: Optional[str] = None) -> LLMResponse:

        prompt = prompt_constructor(prompt)

        logger.debug("Prompt del usuario: " + f"[orange3]{prompt}[/]")

        logger.info("Se evia el mensaje por API")

        try:

            start = perf_counter()
            intereaction = self._client.models.generate_content(
                model=settings.gemini_default_model,
                contents= prompt,
                config= types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=SQLAnswer | InvalidAnswerScheme,
                    temperature= temperature_validator(self.temperature),
                    max_output_tokens=self.max_output_tokens,
                    system_instruction=self.system_prompt))

            latency = round(perf_counter() - start,4)

            logger.info("Llamada exitosa!")

            logger.debug(f"Respuesta generada por el modelo:\n[bold yellow]{intereaction.parsed.model_dump_json(indent=4)}[/]")

            return LLMResponse(
                text = intereaction.parsed,
                provider= "GEMINI",
                model = settings.gemini_default_model,
                latency= float(latency),
                input_tokens= int(intereaction.usage_metadata.prompt_token_count or 0),
                thinking_tokens= int(intereaction.usage_metadata.thoughts_token_count or 0),
                output_tokens= int(intereaction.usage_metadata.candidates_token_count or 0),
                total_tokens= int(intereaction.usage_metadata.total_token_count or 0)
            )
        
        except Exception as e:
            latency = round(perf_counter() - start, 4)
            logger.error(f"Error el parseo de la respuesta: {e}")
            
            if intereaction and hasattr(intereaction, 'usage_metadata'):
  
                return LLMResponse(
                    text=None,
                    provider="GEMINI",
                    model=settings.gemini_default_model,
                    latency= float(latency),
                    input_tokens= int(intereaction.usage_metadata.prompt_token_count or 0),
                    thinking_tokens= int(intereaction.usage_metadata.thoughts_token_count or 0),
                    output_tokens= int(intereaction.usage_metadata.candidates_token_count or 0),
                    total_tokens= int(intereaction.usage_metadata.total_token_count or 0)
                )
            
            # Si intereaction es None, la llamada falló antes de recibir respuesta (0 tokens)
            raise EmptyRespondError
