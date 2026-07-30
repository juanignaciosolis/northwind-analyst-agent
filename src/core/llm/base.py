from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class LLMResponse:
    
    provider: str
    model: str
    latency: int
    input_tokens: int
    thinking_tokens: int
    output_tokens: int
    total_tokens: int
    text: Optional[str] = None



class LLMCliente(ABC):

    def __init__(self, system_prompt: str = None, temperature: float = 0.2, max_output_tokens: int = None):
        self.system_prompt = system_prompt
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens

    @abstractmethod
    def send_message(self, prompt: str) -> LLMResponse:
        pass
