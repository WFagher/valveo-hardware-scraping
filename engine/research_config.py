"""Load the YAML rule files (requirements, sources, scoring) from config/."""
from __future__ import annotations

from pathlib import Path

import yaml


def _load(config_dir: Path, name: str) -> dict:
    path = config_dir / name
    if not path.is_file():
        raise FileNotFoundError(f"Config file not found: {path}")
    return yaml.safe_load(path.read_text())


def load_requirements(config_dir: Path) -> dict:
    return _load(config_dir, "requirements.yaml")


def load_sources(config_dir: Path) -> dict:
    return _load(config_dir, "sources.yaml")


def load_scoring(config_dir: Path) -> dict:
    return _load(config_dir, "scoring_weights.yaml")
