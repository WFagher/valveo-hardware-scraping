"""Discovery cycle shared by the CLI and the scheduler."""
from __future__ import annotations

from collections.abc import Callable

import yaml

from .config import Config
from .crawlers.fetcher import fetch_text
from .extractors.spec_extractor import extract_controller
from .llm.ollama_client import OllamaClient
from .models import Controller
from .store import DeviceStore


def _seed_urls(cfg: Config) -> list[str]:
    data = yaml.safe_load((cfg.config_dir / "seed_urls.yaml").read_text())
    return data.get("urls", [])


def run_discovery_cycle(
    cfg: Config, *, on_result: Callable[[str, Controller | None], None] | None = None
) -> tuple[int, int]:
    urls = _seed_urls(cfg)
    store = DeviceStore(cfg.db_path())
    stored = 0
    try:
        with OllamaClient(cfg.ollama_host) as ol:
            for url in urls:
                text = fetch_text(url)
                controller = extract_controller(
                    text, ollama=ol, model=cfg.chat_model, source_url=url
                )
                if controller is not None:
                    store.upsert(controller)
                    stored += 1
                if on_result is not None:
                    on_result(url, controller)
    finally:
        store.close()
    return stored, len(urls)
