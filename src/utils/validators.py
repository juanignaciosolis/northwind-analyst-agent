from .errors import TypePromptError, EmptyPromptError, TemperatureTypeError, TemperatureLimitsError, ShorterLenghtPromptError, LongerLenghtPromptError
import re
from src.schemas.output_schemas import SQLAnswer, InvalidAnswerScheme

def message_validator(mensaje: str) -> str:
    if mensaje in (None, ""):
        raise EmptyPromptError
    if not isinstance(mensaje, str):
        raise TypePromptError
    if len(mensaje) <= 10:
        raise ShorterLenghtPromptError
    if len(mensaje) >= 5000:
        raise LongerLenghtPromptError

    mensaje = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", mensaje)
    
    clean_mesagge = mensaje.strip()
    
    return clean_mesagge


def temperature_validator(temperature: float | int) -> float | int:

    if not isinstance(temperature, (float,int)):
        raise TemperatureTypeError

    if temperature < 0 or temperature > 2:
        raise TemperatureLimitsError
    
    return temperature

def aplicar_reglas(resultado: SQLAnswer | InvalidAnswerScheme) -> SQLAnswer | InvalidAnswerScheme:
    if resultado.confianza < 0.65:
        resultado.human_revision = True

    return resultado
