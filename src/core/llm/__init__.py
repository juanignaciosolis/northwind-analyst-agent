from .base import LLMCliente, LLMResponse
from .gemini import GeminiClient
from .openai import OpenAIClient
from typing import Callable, Any

import os

from dotenv import load_dotenv
from pathlib import Path


load_dotenv(Path(__file__).resolve().parents[3])


def get_llm_client(*args,**kwargs) -> LLMCliente:
    try:
        providor = os.getenv("LLM_PROVIDER")
    except:
        raise "Falta definir al PROVIDOR como variable de entorno"

    if providor == "GEMINI":
        return GeminiClient(*args,**kwargs)
    elif providor == "OPENAI":
        return OpenAIClient(*args,**kwargs)
    else:
        raise "LLM PROVIDER no implementado"


__all__ = ["get_llm_client"]

