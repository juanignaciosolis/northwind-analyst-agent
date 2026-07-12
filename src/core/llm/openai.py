from logging import Logger
from src.utils.logger import setup_logger

logger: Logger = setup_logger(name=__name__)

from openai import OpenAI
import os
from time import perf_counter
from typing import Optional


from .base import LLMCliente, LLMResponse
from src.utils.validators import prompt_validator, temperature_validator
from src.utils.decorators import retry_backoff
from src.utils.tokenomics import auditar_tokenomics

class OpenAIClient(LLMCliente):
    def __init__(self, system_prompt : Optional[str] = None, temperature: float = 0.2, max_output_tokens: int = None):

        logger.info("Se inicializa el cliente de OpenAI...")
        logger.info(f"Configuracion:\nSystem Prompt - {"Contiene" if system_prompt else "No contiene"}\nTemperature - {temperature}\nMax. Output Tokens - {max_output_tokens}")
     
        super().__init__(system_prompt, 
                         temperature_validator(temperature),
                         max_output_tokens)


        self._client = OpenAI(api_key = os.getenv("OPENAI_API_KEY"))

    auditar_tokenomics
    retry_backoff(3,2)
    def send_message(self, prompt: str, id: Optional[str] = None) -> LLMResponse:

        logger.info("Se evia el mensaje por API")

        logger.info(f"Prompt: {prompt}")


        messages = []

        if self.system_prompt:
            messages.append(
            {
                "role": "developer",
                "content": self.system_prompt
            })

        messages.append(
            {
                "role": "user",
                "content": prompt_validator(prompt)
            })

        start = perf_counter()
        intereaction = self._client.responses.create(
            model = os.getenv("OPENAI_MODEL"),
            input = messages,
            max_output_tokens = self.max_output_tokens
        )

        latency = round(perf_counter() - start,2)

        logger.info("Llamada exitosa!")

        
        return LLMResponse(
            text = intereaction.output_text,
            provider= os.getenv("PROVIDER"),
            model = os.getenv("GEMINI_MODEL"),
            latency= float(latency),
            input_tokens= int(intereaction.usage.input_tokens or 0),
            thinking_tokens= int(intereaction.usage.output_tokens_details.reasoning_tokens or 0),
            output_tokens= int(intereaction.usage.output_tokens or 0),
            total_tokens= int(intereaction.usage.total_tokens or 0)
        )
    

    