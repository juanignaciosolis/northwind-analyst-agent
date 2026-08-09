import asyncio
from dataclasses import asdict, dataclass
import time
from dataclasses import dataclass
from typing import Optional, Protocol, AsyncIterator

@dataclass(frozen=True)
class GenerationResult:
    
    provider: str
    model: str
    latency: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    text: str
    finish_reason: str = "stop"

    def to_dict(self) -> dict:
        return asdict(self)



class LLMProvider(Protocol):

    def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.2,
        max_output_tokens: int | None = None
    ) -> GenerationResult:
        ...

    async def agenerate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.2,
        max_output_tokens: int | None = None
    ) -> GenerationResult:
        ...

    async def astream(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.2,
        max_output_tokens: int | None = None
    ) -> AsyncIterator[str]:
        ...