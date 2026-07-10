from google import genai
from google.genai import types
from typing import Optional
import os
from time import perf_counter


from base import LLMCliente, LLMResponse


class GeminiClient(LLMCliente):
    def __init__(self, system_prompt : Optional[str] = None, temperature: float = 0.2, max_output_tokens: int = None):
        
        super().__init__(system_prompt, temperature, max_output_tokens)


        self._client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    def send_message(self, prompt: str, id: Optional[str] = None) -> LLMResponse:

        start = perf_counter()
        intereaction = self._client.interactions.create(
            model= os.getenv("GEMINI_MODEL"),
            system_instruction= prompt,
            temperature = self.temperature,
            max_output_tokens = self.max_output_tokens,
            previous_interaction_id = id
        )

        latency = perf_counter() - start
        
        return LLMResponse(
            text = intereaction.output_text,
            provider= os.getenv("PROVIDER"),
            model = os.getenv("GEMINI_MODEL"),
            latency= latency,
            input_tokens= intereaction.usage.total_input_tokens,
            thinking_tokens= intereaction.usage.total_thought_tokens,
            output_tokens= intereaction.usage.total_output_tokens,
            total_tokens=intereaction.usage.total_tokens
        )
    

    