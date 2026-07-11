from logging import Logger
from src.utils.logger import setup_logger

logger: Logger = setup_logger(name=__name__)

from google import genai
from google.genai import types
from typing import Optional
import os
from time import perf_counter


from .base import LLMCliente, LLMResponse
from src.utils.validators import prompt_validator, temperature_validator



class GeminiClient(LLMCliente):
    def __init__(self, system_prompt : Optional[str] = None, temperature: float = 0.2, max_output_tokens: int = None):

        logger.info("Se inicializa el cliente de Gemini...")
        logger.info(f"Configuracion:\nSystem Prompt - {system_prompt}\nTemperature - {temperature}\nMax. Output Tokens - {max_output_tokens}")


        super().__init__(system_prompt, 
                         temperature,
                         max_output_tokens)

        self._client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    def send_message(self, prompt: str, id: Optional[str] = None) -> LLMResponse:

        logger.info("Se evia el mensaje por API")

        logger.info(f"Prompt: {prompt}")


        start = perf_counter()
        intereaction = self._client.models.generate_content(
            model=os.getenv("GEMINI_MODEL"),
            contents= prompt_validator(prompt),
            config= types.GenerateContentConfig(
                temperature= temperature_validator(self.temperature),
                max_output_tokens=self.max_output_tokens,
                system_instruction=self.system_prompt))

        latency = perf_counter() - start

        logger.info("Llamada exitosa!")
        
        return LLMResponse(
            text = intereaction.text,
            provider= os.getenv("PROVIDER"),
            model = os.getenv("GEMINI_MODEL"),
            latency= latency,
            input_tokens= intereaction.usage_metadata.prompt_token_count,
            thinking_tokens= intereaction.usage_metadata.thoughts_token_count,
            output_tokens= intereaction.usage_metadata.candidates_token_count,
            total_tokens=intereaction.usage_metadata.total_token_count
        )
    

    ''