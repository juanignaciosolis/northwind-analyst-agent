from typing import  AsyncIterator
import asyncio
import time

from src.core.llm.contract import GenerationResult
from src.utils.errors import (
    InvalidProviderResponseError,
    InvalidRequestError,
    ProviderConfigurationError,
    ProviderTimeoutError,
    RateLimitError,
    TransientProviderError,
)


class FakeProvider:
    """Provider determinístico para aprender y testear sin red ni costo."""

    def __init__(
        self,
        model: str = "fake-llm",
        *,
        delay_seconds: float = 0.03,
        failures: list[str] | None = None,
    ):
        self.model = model
        self.delay_seconds = delay_seconds
        self.failures = list(failures or [])
        self.active_calls = 0
        self.max_active_calls = 0

    def _validate(self, prompt: str) -> None:
        if not isinstance(prompt, str) or not prompt.strip():
            raise InvalidRequestError("El prompt no puede estar vacío")

    def _maybe_fail(self) -> None:
        if not self.failures:
            return
        failure = self.failures.pop(0)
        mapping = {
            "rate_limit": RateLimitError("429 simulado: demasiadas solicitudes"),
            "transient": TransientProviderError("503 simulado: proveedor no disponible"),
            "timeout": ProviderTimeoutError("timeout simulado por el provider"),
            "empty": InvalidProviderResponseError("respuesta simulada vacía"),
            "config": ProviderConfigurationError("credencial simulada inválida"),
        }
        raise mapping[failure]

    @staticmethod
    def _answer(prompt: str) -> str:
        marker = "NUEVO MENSAJE DEL USUARIO"
        if marker in prompt:
            tail = prompt.split(marker, 1)[1]
            user_text = tail.split("Respondé considerando el historial reciente.", 1)[0].strip()
            return f"Respuesta simulada para: {user_text[:120]}"
        last_line = next(
            (line.strip() for line in reversed(prompt.splitlines()) if line.strip()),
            prompt.strip(),
        )
        return f"Respuesta simulada para: {last_line[:120]}"

    def generate(self, prompt: str, *, system: str | None = None, temperature: float = 0.2, max_output_tokens: int | None = None) -> GenerationResult:
        self._validate(prompt)
        started = time.perf_counter()
        time.sleep(self.delay_seconds)
        self._maybe_fail()
        text = self._answer(prompt)
        return GenerationResult(
            text=text,
            model=self.model,
            provider="fake",
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
            input_tokens=max(1, len(prompt.split())),
            output_tokens=max(1, len(text.split())),
        )

    async def agenerate(self, prompt: str, *, system: str | None = None, temperature: float = 0.2, max_output_tokens: int | None = None) -> GenerationResult:
        self._validate(prompt)
        self.active_calls += 1
        self.max_active_calls = max(self.max_active_calls, self.active_calls)
        started = time.perf_counter()
        try:
            await asyncio.sleep(self.delay_seconds)
            self._maybe_fail()
            text = self._answer(prompt)
            return GenerationResult(
                text=text,
                model=self.model,
                provider="fake",
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
                input_tokens=max(1, len(prompt.split())),
                output_tokens=max(1, len(text.split())),
            )
        finally:
            self.active_calls -= 1

    async def astream(self, prompt: str, *, system: str | None = None, temperature: float = 0.2, max_output_tokens: int | None = None) -> AsyncIterator[str]:
        self._validate(prompt)
        self._maybe_fail()
        for word in self._answer(prompt).split():
            await asyncio.sleep(self.delay_seconds / 4)
            yield word + " "
