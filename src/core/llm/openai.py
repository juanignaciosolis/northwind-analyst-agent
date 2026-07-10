from openai import OpenAI
import os
from time import perf_counter
from typing import Optional


from .base import LLMCliente, LLMResponse
from src.utils.validators import prompt_validator, temperature_validator


class OpenAIClient(LLMCliente):
    def __init__(self, system_prompt : Optional[str] = None, temperature: float = 0.2, max_output_tokens: int = None):
        
        super().__init__(system_prompt, 
                         temperature_validator(temperature),
                         max_output_tokens)


        self._client = OpenAI(api_key = os.getenv("OPENAI_API_KEY"))


    def send_message(self, prompt: str, id: Optional[str] = None) -> LLMResponse:

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

        latency = perf_counter() - start
        
        return LLMResponse(
            text = intereaction.output_text,
            provider= os.getenv("PROVIDER"),
            model = os.getenv("GEMINI_MODEL"),
            latency= latency,
            input_tokens= intereaction.usage.input_tokens,
            thinking_tokens= intereaction.usage.output_tokens_details.reasoning_tokens,
            output_tokens= intereaction.usage.output_tokens,
            total_tokens=intereaction.usage.total_tokens
        )
    

    