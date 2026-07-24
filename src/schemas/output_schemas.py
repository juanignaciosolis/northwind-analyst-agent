from logging import Logger
from src.utils.logger import setup_logger

logger: Logger = setup_logger(name=__name__)


from pathlib import Path
from pydantic import BaseModel, Field


class AnswerScheme(BaseModel):
    reasonly: str = Field(description="Descripción corta de los pasos razonados para obtener la respuesta",
                          max_length= 300)
    query: str = Field(description="Consulta SQL que responde la pregunta del usuario",
                       max_length= 500)
    human_revision: bool = Field(description="Establecer en True cuando la pregunta sea ambigua, no hay suficientes datos para responderlas o se detecte una solicitud no correspondida")

    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confianza estimada entre 0 y 1."
    )    