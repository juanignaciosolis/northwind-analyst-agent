from logging import Logger
from src.utils.logger import setup_logger

logger: Logger = setup_logger(name=__name__)


from pydantic import BaseModel, Field
from typing import Literal, Optional


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

class AnswerOpenAIScheme(BaseModel):
    type: Literal["sql_success", "invalid_query"] = Field(
        description="Indica 'sql_success' si se pudo generar la consulta, o 'invalid_query' si ocurrió un error o ambigüedad."
    )
    
    # Campos para caso de Éxito (sql_success)
    query: Optional[str] = Field(
        default=None, 
        description="Consulta SQL válida para PostgreSQL. Solo completar si type == 'sql_success'."
    )
    human_revision: Optional[bool] = Field(
        default=None, 
        description="True si la pregunta era ambigua. Solo completar si type == 'sql_success'."
    )
    confidence: Optional[float] = Field(
        default=None, 
        ge=0.0, 
        le=1.0, 
        description="Nivel de confianza entre 0 y 1."
    )

    # Campos para caso de Error (invalid_query)
    error: Optional[str] = Field(
        default=None, 
        description="Título corto del problema. Solo completar si type == 'invalid_query'."
    )
    resumen: Optional[str] = Field(
        default=None, 
        description="Explicación sencilla del error. Solo completar si type == 'invalid_query'."
    )
    evidence: Optional[list[str]] = Field(
        default=None, 
        description="Extractos o palabras clave del prompt del usuario que causaron el error. Solo completar si type == 'invalid_query'."
    )