from logging import Logger
from src.utils.logger import setup_logger

logger: Logger = setup_logger(name=__name__)


from pathlib import Path
from pydantic import BaseModel, Field
from typing import Literal


class SQLAnswer(BaseModel):
    type: Literal["sql_success"] = Field(default="sql_success",
        description="Identificador para respuestas SQL válidas")
    query: str = Field(description="Consulta SQL que responde la pregunta del usuario",
                       max_length= 500)
    human_revision: bool = Field(description="Establecer en True cuando la pregunta sea ambigua, no hay suficientes datos para responderla")
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confianza estimada entre 0 y 1."
    ) 
class InvalidAnswerScheme(BaseModel):
    type: Literal["invalid_query"] = Field(
        default="invalid_query",
        description="Identificador para respuestas donde no se pudo generar la consulta")
    error: str = Field(description="Titulo del error, problema o inconveniente")
    resumen: str = Field(description="Descripcion sencilla y corta del error, problema o incoveniente",
                         max_length= 300)
    evidence: list[str] = Field(description="Citar de la pregunta del usuario evidencias del problema",
                                min_length=1, max_length=3)   
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confianza estimada entre 0 y 1."
    ) 

class AnswerWrapper(BaseModel):
    payload: SQLAnswer | InvalidAnswerScheme = Field(
        discriminator="type",
        description="Resultado del procesamiento: la consulta generada o el error detallado"
    )