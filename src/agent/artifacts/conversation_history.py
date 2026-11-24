from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
import time
from typing import Any, Literal
from google import genai
from google.genai import types

from src.settings import settings


Role = Literal["user", "assistant"]

DEFAULT_SUMMARY_MODEL = "gemini-3.1-flash-lite"
DEFAULT_STORAGE_DIR = Path(__file__).resolve().parent / 'conversation_history'
DEFAULT_SUMMARY_SYSTEM = (
    "Eres un asistente de compactación de historial de conversacion "
    "Tu objetivo es crea un resumen breve, preciso y factual con los datos proporcioandos."
    "Conserva tablas, métricas, filtros, decisiones y hallazgos clave;"
    "omite saludos y relleno."
    "Responde solo con el resumen."
)


def _sanitizar_identificador(session_id: str) -> str:
    limpio = re.sub(r"[^A-Za-z0-9._-]+", "_", session_id.strip())
    return limpio.strip("._") or "default_session"


@dataclass
class Message:
    role: Role
    content: str

    def to_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass
class Conversation:
    session_id: str
    summary_model: str = DEFAULT_SUMMARY_MODEL
    messages: list[Message] = field(default_factory=list)
    summary: str = ""
    storage_dir: Path | str = DEFAULT_STORAGE_DIR
    storage_path: Path | str | None = None
    auto_save: bool = True
    _genai_client: genai.Client | None = field(default=None, init=False, repr=False)
    _explicit_summary_model: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.summary_model != DEFAULT_SUMMARY_MODEL:
            self._explicit_summary_model = True
        if self.json_path.exists():
            self.load()
        elif self.auto_save:
            self.save()

    @property
    def json_path(self) -> Path:
        if self.storage_path is not None:
            return Path(self.storage_path)
        base_dir = Path(self.storage_dir)
        filename = f"conversation_{_sanitizar_identificador(self.session_id)}.json"
        return base_dir / filename

    def save(self) -> Path:
        """Guarda el estado conversacional de la sesión en disco en formato JSON."""
        target = self.json_path
        target.parent.mkdir(parents=True, exist_ok=True)

        payload: dict[str, Any] = {
            "session_id": self.session_id,
            "summary_model": self.summary_model,
            "summary": self.summary,
            "messages": [msg.to_dict() for msg in self.messages],
        }

        tmp_path = target.with_name(f".{target.name}.{os.getpid()}.tmp")
        with tmp_path.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, target)
        return target

    def load(self) -> bool:
        """Carga el estado conversacional desde el JSON si existe."""
        target = self.json_path
        if not target.exists():
            return False

        with target.open("r", encoding="utf-8") as fh:
            data = json.load(fh)

        if not isinstance(data, dict):
            return False

        if not self._explicit_summary_model and isinstance(data.get("summary_model"), str) and data["summary_model"].strip():
            self.summary_model = data["summary_model"].strip()

        if isinstance(data.get("summary"), str):
            self.summary = data["summary"]

        raw_messages = data.get("messages")
        if isinstance(raw_messages, list):
            cargados: list[Message] = []
            for item in raw_messages:
                if isinstance(item, dict) and item.get("role") in ("user", "assistant"):
                    cargados.append(
                        Message(
                            role=item["role"],
                            content=str(item.get("content", "")),
                        )
                    )
            self.messages = cargados

        return True

    def _get_client(self) -> genai.Client:
        if self._genai_client is None:
            self._genai_client = genai.Client(api_key=settings.gemini_api_key_value())
        return self._genai_client

    def _generate_summary_text(
        self,
        prompt: str,
        *,
        model: str,
        temperature: float,
        max_output_tokens: int,
        retries: int = 2,
    ) -> str:
        client = self._get_client()
        config = types.GenerateContentConfig(
            system_instruction=DEFAULT_SUMMARY_SYSTEM,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )

        last_exc: Exception | None = None
        for attempt in range(retries + 1):
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=config,
                )
                return (response.text or "").strip()
            except Exception as exc:
                last_exc = exc
                if attempt < retries:
                    time.sleep(0.4 * (2**attempt))

        raise RuntimeError(f"Error al generar resumen con Gemini ({model})") from last_exc

    def add(self, role: Role, content: str) -> None:
        self.messages.append(Message(role=role, content=content))
        if self.auto_save:
            self.save()

    def recent(self, max_messages: int = 10) -> list[Message]:
        if max_messages <= 0:
            return []
        return self.messages[-max_messages:]

    def as_dicts(self, max_messages: int = 10) -> list[dict[str, str]]:
        """Devuelve el resumen (con rol 'assistant' si existe) + los últimos `max_messages` mensajes."""
        items: list[dict[str, str]] = []

        clean_summary = self.summary.strip()
        if clean_summary:
            items.append({
                "role": "assistant",
                "content": f"Resumen de conversaciones anteriores:\n{clean_summary}",
            })

        items.extend(message.to_dict() for message in self.recent(max_messages))
        return items

    def compact(
        self,
        *,
        model: str | None = None,
        keep_last: int = 10,
        summary_item_chars: int = 400,
        max_output_tokens: int = 384,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        """Compacta mensajes antiguos encadenándolos con `self.summary` y deja `keep_last` recientes."""
        if keep_last < 0 or summary_item_chars <= 0:
            raise ValueError("keep_last debe ser >= 0 y summary_item_chars > 0")

        if len(self.messages) <= keep_last:
            if self.auto_save:
                self.save()
            return {
                "summary": self.summary,
                "history": self.as_dicts(keep_last if keep_last > 0 else 10),
                "compacted_count": 0,
            }

        old_messages = self.messages[:-keep_last] if keep_last > 0 else list(self.messages)
        recent_messages = self.messages[-keep_last:] if keep_last > 0 else []

        formatted_turns = "\n".join(
            f"{msg.role}: {' '.join(msg.content.split())[:summary_item_chars]}"
            for msg in old_messages
        )

        prompt_parts: list[str] = []
        if self.summary.strip():
            prompt_parts.append(f"Resumen previo:\n{self.summary.strip()}")
        prompt_parts.append(f"Mensajes anteriores a incorporar:\n{formatted_turns}")
        prompt_resumen = "\n\n".join(prompt_parts)

        target_model = model or self.summary_model
        new_summary = self._generate_summary_text(
            prompt_resumen,
            model=target_model,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )

        if new_summary:
            self.summary = new_summary
        else:
            fallback = [self.summary.strip()] if self.summary.strip() else []
            fallback.append(formatted_turns)
            self.summary = "\n".join(fallback)

        self.messages = recent_messages

        if self.auto_save:
            self.save()

        return {
            "summary": self.summary,
            "history": self.as_dicts(keep_last if keep_last > 0 else 10),
            "compacted_count": len(old_messages),
        }


def _mostrar_todos_los_mensajes(titulo: str, mensajes: list[Message]) -> None:
    print(f"\n{'#' * 80}")
    print(f"  {titulo} (Total: {len(mensajes)} mensajes)")
    print(f"{'#' * 80}")
    for i, m in enumerate(mensajes, start=1):
        print(f"  #{i:02d} [{m.role}]: {m.content}")


def _mostrar_resultado_compactacion(
    etiqueta: str,
    resumen_previo: str,
    mensajes_que_van_a_resumen: list[Message],
    resumen_resultante: str,
    diez_mensajes_activos: list[dict[str, str]],
) -> None:
    print(f"\n{'=' * 80}")
    print(f"  {etiqueta}")
    print(f"{'=' * 80}")

    print("\n1) LO QUE SE LE PASA AL MODELO RESUMIDOR:")
    print(f"   - Resumen previo: {resumen_previo if resumen_previo else '(ninguno)'}")
    print(f"   - Mensajes viejos que salen de los últimos 10 ({len(mensajes_que_van_a_resumen)}):")
    for m in mensajes_que_van_a_resumen:
        print(f"       * [{m.role}] {m.content}")

    print("\n2) RESUMEN RESULTANTE:")
    print(f"   {resumen_resultante}")

    print(f"\n3) VENTANA ACTIVA — SIEMPRE LOS ÚLTIMOS 10 MENSAJES ({len(diez_mensajes_activos)}):")
    for i, item in enumerate(diez_mensajes_activos, start=1):
        print(f"   {i:02d}. {item}")


if __name__ == "__main__":
    conv = Conversation(session_id="chat-texto-visible-01")

    bloque_1: list[tuple[Role, str]] = [
        ("user", "Analicemos las ventas de 2025 considerando solo operaciones confirmadas."),
        ("assistant", "Las ventas confirmadas de 2025 suman $48.200.000 en 12.430 operaciones."),
        ("user", "¿Qué rubro vendió más y cuál fue su margen bruto?"),
        ("assistant", "El rubro de electrónica lideró con $19.500.000 (40,5%) y un margen bruto del 28,4%."),
        ("user", "Excluye devoluciones y compara el tercer trimestre contra el cuarto."),
        ("assistant", "Sin devoluciones, el cuarto trimestre creció un 14,2% frente al tercero ($14.100.000 contra $12.345.000)."),
        ("user", "¿Cómo fue el ticket promedio por canal de venta?"),
        ("assistant", "El canal online tuvo un ticket promedio de $3.850 y las sucursales $4.120."),
        ("user", "Decime los tres productos con más unidades vendidas."),
        ("assistant", "Los tres primeros fueron teclado mecánico (4.200 unidades), mouse inalámbrico (3.890) y hub USB-C (3.110)."),
        ("user", "¿Faltó stock de alguno de esos tres productos?"),
        ("assistant", "Sí, el hub USB-C tuvo faltante de stock durante 9 días en noviembre."),
        ("user", "¿Qué margen dejaron los accesorios frente a los periféricos?"),
        ("assistant", "Los accesorios dejaron un 31,0% de margen y los periféricos un 26,8%."),
    ]

    for role, content in bloque_1:
        conv.add(role, content)

    _mostrar_todos_los_mensajes("TODOS LOS MENSAJES DEL BLOQUE 1 (#01 al #14)", conv.messages)

    prev_1 = conv.summary
    van_a_resumen_1 = conv.messages[:-10]
    conv.compact(keep_last=10)

    _mostrar_resultado_compactacion(
        etiqueta="PRIMERA COMPACTACIÓN (#01-#04 al resumen | #05-#14 quedan en los 10)",
        resumen_previo=prev_1,
        mensajes_que_van_a_resumen=van_a_resumen_1,
        resumen_resultante=conv.summary,
        diez_mensajes_activos=conv.as_dicts(10),
    )

    bloque_2_nuevos: list[tuple[Role, str]] = [
        ("user", "Ahora veamos clientes recurrentes, los que compraron al menos tres veces."),
        ("assistant", "Hay 1.820 clientes recurrentes y concentran el 62% de los ingresos."),
        ("user", "¿Qué zona tuvo mayor retención en el último trimestre?"),
        ("assistant", "La zona norte tuvo la mayor retención con un 74,5%."),
        ("user", "¿Cuál fue el costo de adquisición promedio por cliente nuevo?"),
        ("assistant", "El costo de adquisición promedio fue de $1.450 por cliente nuevo."),
        ("user", "¿Qué medio de pago fue el más utilizado en tienda física?"),
        ("assistant", "La tarjeta de crédito en cuotas representó el 54% de las ventas en tienda física."),
        ("user", "¿Hubo diferencia de margen entre ventas en cuotas y pago al contado?"),
        ("assistant", "Sí, el pago al contado dejó 4,5 puntos porcentuales más de margen neto."),
    ]

    for role, content in bloque_2_nuevos:
        conv.add(role, content)

    _mostrar_todos_los_mensajes(
        "TODOS LOS MENSAJES ACUMULADOS ANTES DE COMPACTAR (10 anteriores + 10 nuevos = 20)",
        conv.messages,
    )

    prev_2 = conv.summary
    van_a_resumen_2 = conv.messages[:-10]
    conv.compact(keep_last=10)

    _mostrar_resultado_compactacion(
        etiqueta="SEGUNDA COMPACTACIÓN (Resumen 1 + 10 anteriores al resumen | 10 nuevos quedan activos)",
        resumen_previo=prev_2,
        mensajes_que_van_a_resumen=van_a_resumen_2,
        resumen_resultante=conv.summary,
        diez_mensajes_activos=conv.as_dicts(10),
    )