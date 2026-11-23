import json
import uuid
from typing import Any, Literal
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime


class InMemoryDataStore:
    def __init__(self) -> None:
        # Cambia la estructura: session_id -> dataset_id -> datos
        self._storage: dict[str, dict[str, dict[str, Any]]] = {}
    
    def add(self, df: pd.DataFrame, session_id: str, query: str = "") -> str:
        """Registra un DataFrame para una sesión específica."""
        if session_id not in self._storage:
            self._storage[session_id] = {}
        
        dataset_id = f"ds_{uuid.uuid4().hex[:8]}"
        self._storage[session_id][dataset_id] = {
            "df": df,
            "query": query,
            "rows": len(df),
            "columns": list(df.columns),
            "created_at": datetime.now().isoformat(),  # <- Nueva
        }
        return dataset_id
    
    def get(self, session_id: str, dataset_id: str | None = None) -> pd.DataFrame | None:
        """Obtiene DataFrame de una sesión específica."""
        if session_id not in self._storage:
            return None
        
        session_data = self._storage[session_id]
        
        if not session_data:
            return None
            
        if dataset_id is None:
            # Último de ESA sesión, no global
            return next(reversed(session_data.values()))["df"]
        
        entry = session_data.get(dataset_id)
        return entry["df"] if entry else None