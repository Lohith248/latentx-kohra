"""Scenario, bot-script and inject-file loading."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from kohra.scenario.schema import Inject, Scenario

REPO_ROOT = Path(__file__).resolve().parents[3]


def parse_scenario(text: str) -> Scenario:
    return Scenario.model_validate(yaml.safe_load(text))


def load_scenario(path: str | Path) -> tuple[Scenario, str]:
    """Return the validated scenario and its raw text (the text is embedded in the run log)."""
    text = Path(path).read_text(encoding="utf-8")
    return parse_scenario(text), text


def load_injects(path: str | Path) -> list[Inject]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or []
    return [Inject.model_validate(d) for d in data]


def load_bot(path: str | Path) -> list[dict[str, Any]]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or []
    return sorted(data, key=lambda d: int(d["tick"]))


def resolve_path(p: str) -> Path:
    path = Path(p)
    return path if path.is_absolute() else REPO_ROOT / path


def export_json_schema(out: Path) -> None:
    out.write_text(json.dumps(Scenario.model_json_schema(), indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    export_json_schema(REPO_ROOT / "scenarios" / "scenario.schema.json")
