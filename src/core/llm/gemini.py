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
from src.utils.decorators import retry_backoff
from src.utils.tokenomics import auditar_tokenomics



class GeminiClient(LLMCliente):
    def __init__(self, system_prompt : Optional[str] = None, temperature: float = 0.2, max_output_tokens: int = None):

        logger.info("Se inicializa el cliente de Gemini...")
        logger.info(f"Configuracion:\nSystem Prompt - {"Contiene" if system_prompt else "No contiene"}\nTemperature - {temperature}\nMax. Output Tokens - {max_output_tokens}")


        super().__init__(system_prompt, 
                         temperature,
                         max_output_tokens)

        self._client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    @auditar_tokenomics
    @retry_backoff(3,2)
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

        latency = round(perf_counter() - start,2)

        logger.info("Llamada exitosa!")
        
        return LLMResponse(
            text = intereaction.text,
            provider= os.getenv("PROVIDER"),
            model = os.getenv("GEMINI_MODEL"),
            latency= float(latency),
            input_tokens= int(intereaction.usage_metadata.prompt_token_count or 0),
            thinking_tokens= int(intereaction.usage_metadata.thoughts_token_count or 0),
            output_tokens= int(intereaction.usage_metadata.candidates_token_count or 0),
            total_tokens= int(intereaction.usage_metadata.total_token_count or 0)
        )
