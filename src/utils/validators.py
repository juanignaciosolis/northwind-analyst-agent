from .errors import TypePromptError, EmptyPromptError, TemperatureTypeError, TemperatureLimitsError, ShorterLenghtPromptError, LongerLenghtPromptError
import re
from src.schemas.output_schemas import SQLAnswer, InvalidAnswerScheme, AnswerOpenAIScheme

import re

SHORT_ACK_TOKENS = {
    "si",
    "sí",
    "no",
    "ok",
    "dale",
    "bueno",
    "bien",
    "claro",
    "exacto",
    "correcto",
    "listo",
    "va",
    "nope",
    "nop",
}

MIN_PROMPT_LENGTH = 11
MAX_PROMPT_LENGTH = 5000

def message_validator(mensaje: str) -> str:
    if mensaje is None:
        raise EmptyPromptError
    if not isinstance(mensaje, str):
        raise TypePromptError

    sanitized = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", mensaje)
    clean_message = sanitized.strip()

    if not clean_message:
        raise EmptyPromptError

    normalized_short = re.sub(r"[.!,?¡¿]+$", "", clean_message.lower()).strip()
    is_short_ack = normalized_short in SHORT_ACK_TOKENS

    if not is_short_ack and len(clean_message) < MIN_PROMPT_LENGTH:
        raise ShorterLenghtPromptError

    if len(clean_message) >= MAX_PROMPT_LENGTH:
        raise LongerLenghtPromptError

    return clean_message


def temperature_validator(temperature: float | int) -> float | int:

    if not isinstance(temperature, (float,int)):
        raise TemperatureTypeError

    if temperature < 0 or temperature > 2:
        raise TemperatureLimitsError
    
    return temperature

def aplicar_reglas(resultado: SQLAnswer | InvalidAnswerScheme | AnswerOpenAIScheme) -> SQLAnswer | InvalidAnswerScheme | AnswerOpenAIScheme:
    if resultado.confianza < 0.65:
        resultado.human_revision = True

    return resultado
