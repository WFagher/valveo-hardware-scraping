"""Runtime config loaded from .env / process environment."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    ollama_host: str
    chat_model: str
    fast_model: str
    embed_model: str
    data_dir: Path
    config_dir: Path

    @classmethod
    def load(cls) -> "Config":
        return cls(
            ollama_host=os.environ.get("OLLAMA_HOST", "http://localhost:11434"),
            chat_model=os.environ.get("OLLAMA_CHAT_MODEL", "llama3.3:70b-instruct-q3_K_M"),
            fast_model=os.environ.get("OLLAMA_FAST_MODEL", "llama3.2:3b"),
            embed_model=os.environ.get("OLLAMA_EMBED_MODEL", "nomic-embed-text"),
            data_dir=Path(os.environ.get("ENGINE_DATA_DIR", "./data")).resolve(),
            config_dir=Path(os.environ.get("ENGINE_CONFIG_DIR", "./config")).resolve(),
        )

    def db_path(self) -> Path:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        return self.data_dir / "devices.sqlite3"
