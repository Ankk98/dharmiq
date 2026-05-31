from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_PROMPTS_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class PromptTemplate:
    name: str
    system: str
    user_template: str
    variables: tuple[str, ...]
    regeneration_section_template: str | None = None

    def render_user(self, **kwargs: Any) -> str:
        missing = [name for name in self.variables if name not in kwargs]
        if missing:
            raise ValueError(f"Missing prompt variables for {self.name}: {missing}")
        return self.user_template.format(**kwargs)

    def render_regeneration_section(self, regeneration_instructions: str | None) -> str:
        if not regeneration_instructions or not self.regeneration_section_template:
            return ""
        return self.regeneration_section_template.format(
            regeneration_instructions=regeneration_instructions.strip(),
        )


@lru_cache
def load_prompt(name: str) -> PromptTemplate:
    path = _PROMPTS_DIR / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")

    with path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}

    return PromptTemplate(
        name=name,
        system=str(raw.get("system", "")).strip(),
        user_template=str(raw.get("user_template", "")).strip(),
        variables=tuple(raw.get("variables", [])),
        regeneration_section_template=(
            str(raw["regeneration_section_template"]).strip()
            if raw.get("regeneration_section_template")
            else None
        ),
    )
