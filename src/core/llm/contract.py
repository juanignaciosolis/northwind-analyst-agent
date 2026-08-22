from dataclasses import asdict, dataclass, field
import uuid
from dataclasses import dataclass
from typing import Protocol, AsyncIterator
from src.schemas.output_schemas import SQLAnswer, InvalidAnswerScheme, AnswerOpenAIScheme

@dataclass(frozen=True)
class GenerationResult:
    
    provider: str
    model: str
    latency: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    text: SQLAnswer | InvalidAnswerScheme | AnswerOpenAIScheme
    finish_reason: str = "stop"
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))

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