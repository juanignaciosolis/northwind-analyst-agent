from dataclasses import asdict, dataclass, field
import uuid
from dataclasses import dataclass
from typing import Protocol, AsyncIterator, Any, Literal
from src.schemas.output_schemas import SQLAnswer, InvalidAnswerScheme, AnswerOpenAIScheme
from src.agent.tools.tools import ToolResult

@dataclass(frozen=True)
class GenerationResult:
    
    provider: str
    model: str
    latency: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    executed: Literal[True,False]
    tool_name: str
    tool_arguments: dict[str,Any]
    final_text: str = None


    def to_dict(self) -> dict:
        return asdict(self)



class LLMProvider(Protocol):

    def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.2,
        max_output_tokens: int | None = None,
        available_tools: list[dict[str, Any]] | None = None,
        tool_results: list[ToolResult] | None = None
    ) -> GenerationResult:
        ...

    async def agenerate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.2,
        max_output_tokens: int | None = None,
        available_tools: list[dict[str, Any]] | None = None,
        tool_results: list[ToolResult] | None = None
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