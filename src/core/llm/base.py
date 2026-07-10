from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass(frozen=True)
class LLMResponse:
    text: str
    provider: str
    model: str
    latency: int
    input_tokens: int
    thinking_tokens: int
    output_tokens: int
    total_tokens: int



class LLMCliente(ABC):

    def __init__(self, system_prompt: str = None, temperature: float = 0.2, max_output_tokens: int = None):
        self.system_prompt = system_prompt
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens

    @abstractmethod
    def send_message(self, prompt: str) -> LLMResponse:
        pass
