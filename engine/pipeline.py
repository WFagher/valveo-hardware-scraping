"""Discovery / prospect / full-cycle pipelines shared by the CLI and the scheduler."""
from __future__ import annotations

from collections.abc import Callable

import yaml

from .config import Config
from .crawlers.discovery import load_queries, prospect_urls
from .crawlers.fetcher import fetch_text
from .enrich import enrich_controller
from .extractors.spec_extractor import extract_controller
from .llm.ollama_client import OllamaClient
from .models import Controller
from .outputs.report import write_shortlist_report
from .store import DeviceStore


def _seed_urls(cfg: Config) -> list[str]:
    data = yaml.safe_load((cfg.config_dir / "seed_urls.yaml").read_text())
    return data.get("urls", [])


def _preserve_enrichment(fresh: Controller, existing: Controller) -> Controller:
    """Carry enrichment fields (origin/cert/oem/rebrand/sources) from an existing
    record onto a freshly-extracted one, so re-discovery never wipes enrichment."""
    data = fresh.model_dump()
    ex = existing.model_dump()
    if data.get("country_of_origin") is None:
        data["country_of_origin"] = ex.get("country_of_origin")
    for block in ("cert", "oem"):
        for key, val in (ex.get(block) or {}).items():
            if data[block].get(key) is None and val is not None:
                data[block][key] = val
    if data.get("rebrand_path") == "unknown" and ex.get("rebrand_path") not in (None, "unknown"):
        data["rebrand_path"] = ex["rebrand_path"]
    data["sources"] = list(dict.fromkeys((data.get("sources") or []) + (ex.get("sources") or [])))
    return Controller.model_validate(data)


def run_discovery_cycle(
    cfg: Config, *, on_result: Callable[[str, Controller | None], None] | None = None
) -> tuple[int, int]:
    urls = _seed_urls(cfg)
    store = DeviceStore(cfg.db_path())
    stored = 0
    try:
        with OllamaClient(cfg.ollama_host) as ol:
            for url in urls:
                try:
                    text = fetch_text(url)
                    controller = extract_controller(
                        text, ollama=ol, model=cfg.chat_model, source_url=url
                    )
                except Exception:
                    controller = None  # one unreachable URL must not abort the whole crawl
                if controller is not None:
                    existing = store.get(controller.key)
                    if existing is not None:
                        controller = _preserve_enrichment(controller, existing)
                    store.upsert(controller)
                    stored += 1
                if on_result is not None:
                    on_result(url, controller)
    finally:
        store.close()
    return stored, len(urls)


def run_prospect_cycle(
    cfg: Config,
    *,
    on_result: Callable[[str, Controller | None], None] | None = None,
    max_new: int = 12,
) -> tuple[int, int]:
    """Open-ended discovery: search the web for NEW device pages, extract, and store
    the ones that are actually cellular controllers (the core requirement).

    Caps work per cycle to `max_new` URLs; the rest are picked up on later cycles
    (the seen table makes this resume cleanly)."""
    queries = load_queries(cfg.config_dir)
    store = DeviceStore(cfg.db_path())
    stored = 0
    try:
        urls = prospect_urls(queries, is_seen=store.is_seen)[:max_new]
        with OllamaClient(cfg.ollama_host) as ol:
            for url in urls:
                store.mark_seen(url)  # never re-process this page
                try:
                    text = fetch_text(url)
                    controller = extract_controller(
                        text, ollama=ol, model=cfg.chat_model, source_url=url
                    )
                except Exception:
                    controller = None
                if controller is not None and controller.cellular:
                    existing = store.get(controller.key)
                    if existing is not None:
                        controller = _preserve_enrichment(controller, existing)
                    store.upsert(controller)
                    stored += 1
                if on_result is not None:
                    on_result(url, controller)
    finally:
        store.close()
    return stored, len(urls)


def _enrich_new(cfg: Config) -> int:
    """Enrich each device exactly once (tracked via the seen table)."""
    store = DeviceStore(cfg.db_path())
    enriched = 0
    try:
        targets = [c for c in store.all() if not store.is_seen("enriched:" + c.key)]
        if targets:
            with OllamaClient(cfg.ollama_host) as ol:
                for c in targets:
                    updated = enrich_controller(c, ollama=ol, model=cfg.chat_model)
                    store.upsert(updated)
                    store.mark_seen("enriched:" + c.key)
                    enriched += 1
    finally:
        store.close()
    return enriched


def run_full_cycle(cfg: Config, *, timestamp: str = "") -> dict:
    """One autonomous pass: prospect (open search) + re-crawl seeds + enrich new +
    write the live shortlist report. This is what the 24/7 scheduler runs."""
    prospected, _ = run_prospect_cycle(cfg)
    discovered, _ = run_discovery_cycle(cfg)
    enriched = _enrich_new(cfg)
    report = write_shortlist_report(cfg, timestamp=timestamp)
    return {
        "prospected": prospected,
        "discovered": discovered,
        "enriched": enriched,
        "report": str(report),
    }
