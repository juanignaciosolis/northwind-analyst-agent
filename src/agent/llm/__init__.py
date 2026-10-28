from .gemini import GeminiClient
from .openai import OpenAIClient
#from .fake import FakeProvider
from src.settings import settings


def build_provider(settings):
    if getattr(settings,"default_provider", None) == "GEMINI":
        return GeminiClient(settings.api_key_value(), settings.gemini_default_model)
    if getattr(settings,"default_provider", None) == "OPENAI":
        return OpenAIClient(settings.api_key_value(), settings.openai_default_model)
#    return FakeProvider(model=f"fake:{settings.default_model}")
    raise ValueError(f"Proveedor no soportado o no configurado: '{settings.default_provider}'")

__all__ = ["build_provider"]

