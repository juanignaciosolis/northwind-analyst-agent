from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from src.utils.database import create_db_pool  # ajusta al nombre de tu módulo/función de pool


ALLOWED_MEMORY_KINDS: set[str] = {
    "user_preference",
    "business_rule",
    "user_correction",
    "kpi_definition",
    "analysis_pattern",
}


@dataclass(frozen=True)
class MemoryScope:
    user_id: str
    project_id: str = ""
    course_id: str = ""
    session_id: str = ""


@dataclass(frozen=True)
class MemoryCandidate:
    kind: str
    key: str
    value: Any
    source: str = "user_explicit"
    confidence: float = 1.0
    priority: int = 5
    expires_at: datetime | None = None
    confirmed: bool = True
    durable: bool = True
    sensitive: bool = False
    persist_allowed: bool = True


@dataclass(frozen=True)
class WriteDecision:
    allowed: bool
    reason: str


def _validate_kind(kind: Any) -> str:
    if not isinstance(kind, str) or not kind.strip():
        raise ValueError(
            f"El tipo de memoria ('kind') es obligatorio. Válidos: {sorted(ALLOWED_MEMORY_KINDS)}."
        )
    normalized = kind.strip()
    if normalized not in ALLOWED_MEMORY_KINDS:
        raise ValueError(
            f"Tipo de memoria no permitido '{normalized}'. Válidos: {sorted(ALLOWED_MEMORY_KINDS)}."
        )
    return normalized


def evaluate_write(candidate: MemoryCandidate) -> WriteDecision:
    """Evalúa si un candidato cumple las reglas de persistencia durable."""
    if not candidate.persist_allowed:
        return WriteDecision(False, "Persistencia deshabilitada para este candidato.")
    if candidate.sensitive:
        return WriteDecision(False, "No se permite persistir información sensible.")
    if not candidate.confirmed:
        return WriteDecision(False, "Solo se persisten datos confirmados explícitamente.")
    if not candidate.durable:
        return WriteDecision(False, "Solo se persisten datos durables (no transitorios).")
    try:
        _validate_kind(candidate.kind)
    except ValueError as exc:
        return WriteDecision(False, str(exc))
    if not candidate.key or not candidate.key.strip():
        return WriteDecision(False, "La clave ('key') de memoria no puede estar vacía.")
    if not (0.0 <= float(candidate.confidence) <= 1.0):
        return WriteDecision(False, "La confianza ('confidence') debe estar entre 0.0 y 1.0.")
    return WriteDecision(True, "Aprobado para persistencia.")


def _normalize_json_payload(value: Any) -> dict[str, Any] | list[Any] | str | int | float | bool | None:
    """Garantiza un valor compatible con JSONB (envolviendo escalares si hace falta)."""
    if value is None or isinstance(value, (dict, list, str, int, float, bool)):
        return value
    return str(value)


class PostgresMemoryStore:
    """Almacén persistente de memoria del agente sobre `agent_memory.memory`."""

    def __init__(self, pool: ConnectionPool, schema: str = "agent_memory") -> None:
        self.pool = pool
        self.schema = schema

    def _table_ref(self) -> str:
        return f"{self.schema}.memory"

    def write(self, scope: MemoryScope, candidate: MemoryCandidate) -> dict[str, Any]:
        decision = evaluate_write(candidate)
        if not decision.allowed:
            raise ValueError(f"Memoria rechazada: {decision.reason}")

        clean_kind = _validate_kind(candidate.kind)
        memory_id = str(uuid4())
        now = datetime.now(timezone.utc)
        payload = Jsonb(_normalize_json_payload(candidate.value))
        table = self._table_ref()

        query = f"""
            INSERT INTO {table} (
                memory_id,
                user_id,
                project_id,
                course_id,
                session_id,
                kind,
                key,
                value_json,
                source,
                confidence,
                priority,
                created_at,
                updated_at,
                expires_at,
                supersedes,
                status
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL, 'active')
            RETURNING
                memory_id,
                user_id,
                project_id,
                course_id,
                session_id,
                kind,
                key,
                value_json,
                source,
                confidence,
                priority,
                created_at,
                updated_at,
                expires_at,
                supersedes,
                status;
        """

        params = (
            memory_id,
            scope.user_id,
            scope.project_id,
            scope.course_id,
            scope.session_id,
            clean_kind,
            candidate.key.strip(),
            payload,
            candidate.source,
            float(candidate.confidence),
            int(candidate.priority),
            now,
            now,
            candidate.expires_at,
        )

        with self.pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(query, params)
                row = cur.fetchone()
            conn.commit()

        return dict(row) if row else {}

    def retrieve(
        self,
        scope: MemoryScope,
        query: str | None = None,
        kinds: set[str] | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        table = self._table_ref()
        now = datetime.now(timezone.utc)

        clauses = [
            "user_id = %s",
            "project_id = %s",
            "course_id = %s",
            "status = 'active'",
            "(expires_at IS NULL OR expires_at > %s)",
        ]
        params: list[Any] = [scope.user_id, scope.project_id, scope.course_id, now]

        if scope.session_id:
            clauses.append("(session_id = '' OR session_id = %s)")
            params.append(scope.session_id)
        else:
            clauses.append("session_id = ''")

        if kinds is not None:
            validated_kinds = [_validate_kind(k) for k in kinds]
            if not validated_kinds:
                raise ValueError(
                    f"Si se especifica 'kinds', debe contener al menos un tipo válido: {sorted(ALLOWED_MEMORY_KINDS)}."
                )
            clauses.append("kind = ANY(%s)")
            params.append(validated_kinds)

        if query and query.strip():
            pattern = f"%{query.strip()}%"
            clauses.append("(key ILIKE %s OR value_json::text ILIKE %s)")
            params.extend([pattern, pattern])

        params.append(limit)

        sql_query = f"""
            SELECT
                memory_id,
                user_id,
                project_id,
                course_id,
                session_id,
                kind,
                key,
                value_json,
                source,
                confidence,
                priority,
                created_at,
                updated_at,
                expires_at,
                supersedes,
                status
            FROM {table}
            WHERE {" AND ".join(clauses)}
            ORDER BY priority DESC, confidence DESC, updated_at DESC
            LIMIT %s;
        """

        with self.pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(sql_query, params)
                rows = cur.fetchall()

        return [dict(r) for r in rows]

    def supersede(
        self,
        old_memory_id: str,
        scope: MemoryScope,
        candidate: MemoryCandidate,
    ) -> dict[str, Any]:
        decision = evaluate_write(candidate)
        if not decision.allowed:
            raise ValueError(f"Nueva memoria rechazada: {decision.reason}")

        clean_kind = _validate_kind(candidate.kind)
        new_id = str(uuid4())
        now = datetime.now(timezone.utc)
        payload = Jsonb(_normalize_json_payload(candidate.value))
        table = self._table_ref()

        with self.pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    f"""
                    SELECT memory_id
                    FROM {table}
                    WHERE memory_id = %s
                      AND user_id = %s
                      AND project_id = %s
                      AND course_id = %s
                      AND status = 'active'
                    FOR UPDATE;
                    """,
                    (old_memory_id, scope.user_id, scope.project_id, scope.course_id),
                )
                existing = cur.fetchone()
                if not existing:
                    raise LookupError(
                        f"No se encontró memoria activa '{old_memory_id}' para el scope indicado."
                    )

                cur.execute(
                    f"""
                    UPDATE {table}
                    SET status = 'superseded',
                        updated_at = %s
                    WHERE memory_id = %s;
                    """,
                    (now, old_memory_id),
                )

                cur.execute(
                    f"""
                    INSERT INTO {table} (
                        memory_id,
                        user_id,
                        project_id,
                        course_id,
                        session_id,
                        kind,
                        key,
                        value_json,
                        source,
                        confidence,
                        priority,
                        created_at,
                        updated_at,
                        expires_at,
                        supersedes,
                        status
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'active')
                    RETURNING
                        memory_id,
                        user_id,
                        project_id,
                        course_id,
                        session_id,
                        kind,
                        key,
                        value_json,
                        source,
                        confidence,
                        priority,
                        created_at,
                        updated_at,
                        expires_at,
                        supersedes,
                        status;
                    """,
                    (
                        new_id,
                        scope.user_id,
                        scope.project_id,
                        scope.course_id,
                        scope.session_id,
                        clean_kind,
                        candidate.key.strip(),
                        payload,
                        candidate.source,
                        float(candidate.confidence),
                        int(candidate.priority),
                        now,
                        now,
                        candidate.expires_at,
                        old_memory_id,
                    ),
                )
                new_row = cur.fetchone()

            conn.commit()

        return dict(new_row) if new_row else {}

    def delete(self, memory_id: str, scope: MemoryScope) -> bool:
        now = datetime.now(timezone.utc)
        table = self._table_ref()

        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    UPDATE {table}
                    SET status = 'deleted',
                        updated_at = %s
                    WHERE memory_id = %s
                      AND user_id = %s
                      AND project_id = %s
                      AND course_id = %s
                      AND status = 'active';
                    """,
                    (now, memory_id, scope.user_id, scope.project_id, scope.course_id),
                )
                updated = cur.rowcount > 0
            conn.commit()

        return updated


def main() -> None:
    pool = create_db_pool()
    try:
        store = PostgresMemoryStore(pool=pool, schema="agent_memory")
        scope = MemoryScope(
            user_id="test_user",
            project_id="northwind",
            course_id="",
            session_id="",
        )

        # 1. Probar rechazo de política (no durable / sensible)
        bad_candidate = MemoryCandidate(
            kind="user_preference",
            key="temp_filter",
            value="solo hoy",
            durable=False,
        )
        decision = evaluate_write(bad_candidate)
        assert not decision.allowed, "Debería rechazar durable=False"
        print(f"[OK] Política rechazó candidato no durable: {decision.reason}")

        # 2. Guardar memoria válida (write)
        candidate_v1 = MemoryCandidate(
            kind="kpi_definition",
            key="net_revenue_formula",
            value={"formula": "SUM(UnitPrice * Quantity * (1 - Discount))", "currency": "USD"},
            source="user_explicit",
            confidence=0.95,
            priority=8,
        )
        saved_v1 = store.write(scope=scope, candidate=candidate_v1)
        mem_id_v1 = saved_v1["memory_id"]
        print(f"[OK] Memoria guardada: memory_id={mem_id_v1}, key={saved_v1['key']}")

        # 3. Recuperar memoria (retrieve)
        found = store.retrieve(scope=scope, query="net_revenue")
        assert len(found) == 1 and found[0]["memory_id"] == mem_id_v1
        print(f"[OK] Memoria recuperada: {found[0]['value_json']}")

        # 4. Reemplazar atómicamente (supersede)
        candidate_v2 = MemoryCandidate(
            kind="kpi_definition",
            key="net_revenue_formula",
            value={"formula": "SUM(ExtendedPrice)", "currency": "USD"},
            source="user_correction",
            confidence=1.0,
            priority=9,
        )
        saved_v2 = store.supersede(old_memory_id=mem_id_v1, scope=scope, candidate=candidate_v2)
        mem_id_v2 = saved_v2["memory_id"]
        assert saved_v2["supersedes"] == mem_id_v1
        print(f"[OK] Memoria reemplazada: nuevo memory_id={mem_id_v2}, supersedes={saved_v2['supersedes']}")

        # Verificar que retrieve solo traiga la activa (v2)
        active_after = store.retrieve(scope=scope, query="net_revenue")
        assert len(active_after) == 1 and active_after[0]["memory_id"] == mem_id_v2
        print(f"[OK] Solo queda activa la v2: {active_after[0]['value_json']}")

        # 5. Borrado lógico (delete) para dejar limpio
        deleted = store.delete(memory_id=mem_id_v2, scope=scope)
        assert deleted is True
        assert store.retrieve(scope=scope) == []
        print("[OK] Borrado lógico completado y scope limpio.")

    finally:
        pool.close()


if __name__ == "__main__":
    main()