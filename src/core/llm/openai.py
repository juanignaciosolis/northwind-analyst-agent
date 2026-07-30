import logging
from logging import Logger

logger: Logger = logging.getLogger(__name__)

from openai import OpenAI
import os
from time import perf_counter
from typing import Optional


from .base import LLMCliente, LLMResponse
from src.utils.validators import temperature_validator
from src.prompts.user_prompt import prompt_constructor
from src.utils.decorators import retry_backoff
from src.utils.tokenomics import auditar_tokenomics
from src.schemas.output_schemas import AnswerOpenAIScheme
from src.utils.errors import EmptyRespondError


class OpenAIClient(LLMCliente):
    def __init__(self, system_prompt : Optional[str] = None, temperature: float = 0.2, max_output_tokens: int = None):

        logger.info("Se inicializa el cliente de OpenAI...")

        logger.debug(f"Configuracion:\nSystem Prompt - {"Contiene" if system_prompt else "No contiene"}\nTemperature - {temperature}\nMax. Output Tokens - {max_output_tokens}")

        logger.debug(f"[bold yellow]System prompt cargado:[/]\n{system_prompt}")
     
        super().__init__(system_prompt, 
                         temperature_validator(temperature),
                         max_output_tokens)


        self._client = OpenAI(api_key = os.getenv("OPENAI_API_KEY"))

        logger.info("¡Éxito! Cliente instanciado")

    @auditar_tokenomics
    @retry_backoff(3,2)
    def send_message(self, prompt: str, id: Optional[str] = None) -> LLMResponse:

        prompt = prompt_constructor(prompt)

        logger.debug("Prompt: " + f"[orange3]{prompt}[/]")

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
                "content": prompt
            })

        logger.info("Se evia el mensaje por API")

        try:
            start = perf_counter()
            interaction = self._client.beta.chat.completions.parse(
                model = os.getenv("OPENAI_MODEL"),
                messages= messages,
                response_format= AnswerOpenAIScheme,
                max_tokens = self.max_output_tokens
            )

            latency = round(perf_counter() - start,4)

            logger.info("Llamada exitosa!")

            usage = interaction.usage

            parsed_response = interaction.choices[0].message.parsed

            reasoning_tokens = 0
            if usage and hasattr(usage, "completion_tokens_details") and usage.completion_tokens_details:
                reasoning_tokens = getattr(usage.completion_tokens_details, "reasoning_tokens", 0) or 0

            logger.debug(f"Respuesta generada por el modelo:\n[bold yellow]{parsed_response.parsed.model_dump_json(indent=4)}[/]")

            return LLMResponse(
            text=parsed_response, 
            provider=os.getenv("LLM_PROVIDER"),
            model=os.getenv("OPENAI_MODEL"),  
            latency=float(latency),
            input_tokens=int(usage.prompt_tokens if usage else 0), 
            thinking_tokens=int(reasoning_tokens), 
            output_tokens=int(usage.completion_tokens if usage else 0),
            total_tokens=int(usage.total_tokens if usage else 0)
            )
        except Exception as e:
            latency = round(perf_counter() - start, 4)
            logger.error(f"Error en la interacción con OpenAI: {e}")

            if interaction and hasattr(interaction, 'usage'):
                usage = interaction.usage
                return LLMResponse(
                    text=None,
                    provider=os.getenv("LLM_PROVIDER"),
                    model=os.getenv("OPENAI_MODEL"),
                    latency=float(latency),
                    input_tokens=int(usage.prompt_tokens or 0),
                    thinking_tokens=0, 
                    output_tokens=int(usage.completion_tokens or 0),
                    total_tokens=int(usage.total_tokens or 0)
                )

            raise EmptyRespondError