from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any
import json

import yaml

_SKILL_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

SKILL_DIR = Path(__file__).parent

@dataclass(frozen=True)
class SkillSelection:
    selected: str | None
    reason: str
    candidates: list[dict[str, Any]]

def _normalize(text: str) -> str:
    return " ".join(str(text).casefold().split())


def _split_metadata(value: Any) -> list[str]:
    return [
        item.strip()
        for item in str(value or "").split("|")
        if item.strip()
    ]

def read_skill_frontmatter(path: Path) -> dict:
    """Lee el frontmatter YAML sin consumir el cuerpo Markdown."""
    lines = []

    with Path(path).open("r", encoding="utf-8") as handle:
        if handle.readline().strip() != "---":
            raise ValueError(f"{path} no comienza con frontmatter")

        for line in handle:
            if line.strip() == "---":
                break
            lines.append(line)
        else:
            raise ValueError(f"{path} no cierra el frontmatter")

    return yaml.safe_load("".join(lines)) or {}

def skill_catalog(root: Path) -> list[dict]:
    """Construye discovery metadata de Agent Skills."""
    rows = []

    for path in sorted(root.glob("*/SKILL.md")):
        frontmatter = read_skill_frontmatter(path)
        course = frontmatter.get("metadata") or {}

        rows.append({
            "name": frontmatter["name"],
            "description": frontmatter["description"],
            "version": str(course.get("course-version", "unversioned")),
        })

    return rows


class SkillLoader:
    """Loader didáctico compatible con el formato Agent Skills."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.events: list[dict[str, Any]] = []

    def reset_trace(self):
        self.events.clear()

    def _skill_path(self, name: str) -> Path:
        directory = (self.root / name).resolve()

        if directory.parent != self.root.resolve():
            raise ValueError("La Skill debe ser una carpeta directa de la raíz")

        return directory / "SKILL.md"

    def _validate_frontmatter(
        self,
        path: Path,
        frontmatter: dict,
    ) -> None:
        name = frontmatter.get("name")
        description = frontmatter.get("description")

        if not isinstance(name, str) or not _SKILL_NAME.fullmatch(name):
            raise ValueError(f"Nombre Agent Skill inválido: {name!r}")

        if name != path.parent.name:
            raise ValueError(
                "El name del frontmatter debe coincidir con la carpeta"
            )

        if not isinstance(description, str) or not (1 <= len(description) <= 1024):
            raise ValueError("description debe tener entre 1 y 1024 caracteres")

        metadata = frontmatter.get("metadata", {})
        if metadata is not None and not isinstance(metadata, dict):
            raise ValueError("metadata debe ser un mapping")

        for key, value in (metadata or {}).items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise ValueError(
                    "Agent Skills define metadata como string → string"
                )

    def _read_frontmatter(self, path: Path) -> dict:
        """Lee solo metadata: no consume el cuerpo Markdown."""
        lines = []

        with path.open("r", encoding="utf-8") as handle:
            if handle.readline().strip() != "---":
                raise ValueError(f"{path} no comienza con frontmatter")

            for line in handle:
                if line.strip() == "---":
                    break
                lines.append(line)
            else:
                raise ValueError(f"{path} no cierra el frontmatter")

        frontmatter = yaml.safe_load("".join(lines)) or {}
        self._validate_frontmatter(path, frontmatter)

        course = frontmatter.get("metadata") or {}

        self.events.append({
            "event": "metadata_read",
            "skill": frontmatter["name"],
            "version": str(course.get("course-version", "unversioned")),
        })

        return frontmatter

    def _entry_from_frontmatter(self, frontmatter: dict) -> dict:
        course = frontmatter.get("metadata") or {}

        return {
            "name": frontmatter["name"],
            "description": frontmatter["description"],
            "version": str(course.get("course-version", "unversioned")),
            "activation": {
                "when": _split_metadata(course.get("course-activation")),
                "when_not": _split_metadata(
                    course.get("course-negative-signals")
                ),
            },
            "tool_hints": _split_metadata(
                course.get("course-tool-hints")
            ),
            "resources": _split_metadata(
                course.get("course-resources")
            ),
            "tags": _split_metadata(course.get("course-tags")),
        }
    
    def list_summaries(self) -> list[dict]:
        summaries = []

        for path in sorted(self.root.glob("*/SKILL.md")):
            summaries.append(
                self._entry_from_frontmatter(
                    self._read_frontmatter(path)
                )
            )

        return summaries

    def load(self, name: str) -> dict:
        """Carga Nivel 2: frontmatter + cuerpo completo de SKILL.md."""
        path = self._skill_path(name)
        frontmatter = self._read_frontmatter(path)
        entry = self._entry_from_frontmatter(frontmatter)

        text = path.read_text(encoding="utf-8")
        _, _, body = text.split("---", 2)
        body = body.strip()

        if not body:
            raise ValueError("SKILL.md debe contener instrucciones")

        self.events.append({
            "event": "skill_body_load",
            "skill": name,
            "version": entry["version"],
        })

        return {
            **entry,
            "frontmatter": frontmatter,
            "instructions": body,
        }

    def load_resource(
        self,
        name: str,
        relative_path: str,
    ) -> str:
        """Carga Nivel 3 sin permitir escapar del directorio de la Skill."""
        directory = self._skill_path(name).parent
        resource = (directory / relative_path).resolve()

        if resource != directory and directory not in resource.parents:
            raise ValueError("Ruta de recurso fuera de la Skill")

        if not resource.is_file():
            raise FileNotFoundError(relative_path)

        text = resource.read_text(encoding="utf-8")

        self.events.append({
            "event": "resource_load",
            "skill": name,
            "resource": relative_path,
        })

        return text

if __name__ == "__main__":

    skill = SkillLoader(SKILL_DIR)
    skill.reset_trace()
    print(json.dumps(skill.list_summaries(), indent=2, ensure_ascii=False))
    print(json.dumps(skill.load("northwind-dw-analytics"), indent=2, ensure_ascii=False))
    print(json.dumps(skill.load_resource("northwind-dw-analytics", "references/dw-star-schema.md"), indent=2, ensure_ascii=False))