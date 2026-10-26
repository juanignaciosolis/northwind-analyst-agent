import json
import uuid
from typing import Any, Literal
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field


class InMemoryDataStore:
    """Almacén en memoria desacoplado para DataFrames generados en la sesión."""

    def __init__(self) -> None:
        self._storage: dict[str, dict[str, Any]] = {}

    def add(self, df: pd.DataFrame, query: str = "") -> str:
        """Registra un DataFrame y retorna un identificador único."""
        dataset_id = f"ds_{uuid.uuid4().hex[:8]}"
        self._storage[dataset_id] = {
            "df": df,
            "query": query,
            "rows": len(df),
            "columns": list(df.columns),
        }
        return dataset_id

    def get(self, dataset_id: str | None = None) -> pd.DataFrame | None:
        """Obtiene el DataFrame por ID. Si no se indica ID, devuelve el último insertado."""
        if not self._storage:
            return None
        if dataset_id is None:
            return next(reversed(self._storage.values()))["df"]
        entry = self._storage.get(dataset_id)
        return entry["df"] if entry else None

    def list_ids(self) -> list[str]:
        """Devuelve los IDs disponibles en el almacén."""
        return list(self._storage.keys())


class ExecutionContext(BaseModel):
    """Contexto confiable construido por la aplicación."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    user_id: str
    role: Any
    workspace_ids: list[str] = Field(default_factory=list)
    allow_drafts: bool = False
    allow_external_writes: bool = False
    run_id: str = "run-local"

    # Artefacto en memoria excluido de serialización para no romper logs ni trazas
    store: InMemoryDataStore = Field(
        default_factory=InMemoryDataStore, exclude=True
    )