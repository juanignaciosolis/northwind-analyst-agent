from logging import Logger
from src.utils.logger import setup_logger

logger: Logger = setup_logger(name=__name__)

from openai import OpenAI
import os
from time import perf_counter
from typing import Optional


from .base import LLMCliente, LLMResponse
from src.utils.validators import prompt_constructor, temperature_validator
from src.utils.decorators import retry_backoff
from src.utils.tokenomics import auditar_tokenomics
from src.schemas.output_schemas import SQLAnswer, InvalidAnswerScheme
from pydantic import TypeAdapter

answer_validator_router = TypeAdapter(SQLAnswer | InvalidAnswerScheme)
JSON_SCHEMA_UNIFICADO = answer_validator_router.json_schema()

class OpenAIClient(LLMCliente):
    def __init__(self, system_prompt : Optional[str] = None, temperature: float = 0.2, max_output_tokens: int = None):

        logger.info("Se inicializa el cliente de OpenAI...")
        logger.info(f"Configuracion:\nSystem Prompt - {"Contiene" if system_prompt else "No contiene"}\nTemperature - {temperature}\nMax. Output Tokens - {max_output_tokens}")
     
        super().__init__(system_prompt, 
                         temperature_validator(temperature),
                         max_output_tokens)


        self._client = OpenAI(api_key = os.getenv("OPENAI_API_KEY"))

    @auditar_tokenomics
    @retry_backoff(3,2)
    def send_message(self, prompt: str, id: Optional[str] = None) -> LLMResponse:

        logger.info("Se evia el mensaje por API")

        logger.info("Prompt: " + f"[orange3]{prompt}[/]")


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
                "content": prompt_constructor(prompt)
            })

        start = perf_counter()
        interaction = self._client.beta.chat.completions.parse(
            model = os.getenv("OPENAI_MODEL"),
            messages= messages,
            response_format= SQLAnswer | InvalidAnswerScheme,
            max_tokens = self.max_output_tokens
        )

        latency = round(perf_counter() - start,4)

        logger.info("Llamada exitosa!")

        usage = interaction.usage

        reasoning_tokens = 0
        if usage and hasattr(usage, "completion_tokens_details") and usage.completion_tokens_details:
            reasoning_tokens = getattr(usage.completion_tokens_details, "reasoning_tokens", 0) or 0

        return LLMResponse(
        text=interaction.choices[0].message.parsed, 
        provider=os.getenv("LLM_PROVIDER"),
        model=os.getenv("OPENAI_MODEL"),  
        latency=float(latency),
        input_tokens=int(usage.prompt_tokens if usage else 0), 
        thinking_tokens=int(reasoning_tokens), 
        output_tokens=int(usage.completion_tokens if usage else 0),
        total_tokens=int(usage.total_tokens if usage else 0)
        )

    