from __future__ import annotations

import engine.pipeline as pipeline
from engine.config import Config
from engine.models import Controller
from engine.store import DeviceStore


class _DummyOllama:
    def __init__(self, *a, **k):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *e):
        pass


def test_discovery_preserves_enrichment(monkeypatch, tmp_path):
    from engine.models import RebrandPath

    monkeypatch.setenv("ENGINE_DATA_DIR", str(tmp_path / "data"))
    # pre-store an enriched device
    store = DeviceStore(Config.load().db_path())
    enriched = Controller(
        vendor="V", model="M", country_of_origin="China", rebrand_path=RebrandPath.oem_program
    )
    enriched.oem.offered = True
    store.upsert(enriched)
    store.close()

    # discover re-extracts the same device with fresh specs but NO enrichment fields
    monkeypatch.setattr(pipeline, "OllamaClient", _DummyOllama)
    monkeypatch.setattr(pipeline, "_seed_urls", lambda cfg: ["u"])
    monkeypatch.setattr(pipeline, "fetch_text", lambda url, **k: "text")
    monkeypatch.setattr(
        pipeline, "extract_controller",
        lambda text, **kw: Controller(vendor="V", model="M", cellular=True),
    )
    pipeline.run_discovery_cycle(Config.load())

    store = DeviceStore(Config.load().db_path())
    got = store.get("v::m")
    store.close()
    assert got.cellular is True  # fresh spec applied
    assert got.country_of_origin == "China"  # enrichment preserved
    assert got.oem.offered is True
    assert got.rebrand_path is RebrandPath.oem_program


def test_run_discovery_cycle_survives_fetch_error(monkeypatch, tmp_path):
    monkeypatch.setenv("ENGINE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(pipeline, "OllamaClient", _DummyOllama)
    monkeypatch.setattr(pipeline, "_seed_urls", lambda cfg: ["bad", "good"])

    def fake_fetch(url, **k):
        if url == "bad":
            raise Exception("nodename nor servname provided")
        return "text"

    monkeypatch.setattr(pipeline, "fetch_text", fake_fetch)
    monkeypatch.setattr(
        pipeline, "extract_controller", lambda text, **kw: Controller(vendor="V", model="M")
    )
    stored, total = pipeline.run_discovery_cycle(Config.load())
    assert stored == 1 and total == 2  # bad URL skipped, good URL still stored


def test_run_discovery_cycle_stores_only_valid(monkeypatch, tmp_path):
    monkeypatch.setenv("ENGINE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(pipeline, "OllamaClient", _DummyOllama)
    monkeypatch.setattr(pipeline, "_seed_urls", lambda cfg: ["u1", "u2"])
    monkeypatch.setattr(pipeline, "fetch_text", lambda url, **k: "text " + url)
    monkeypatch.setattr(
        pipeline,
        "extract_controller",
        lambda text, **kw: Controller(vendor="V", model="M")
        if "u1" in (kw.get("source_url") or "")
        else None,
    )
    stored, total = pipeline.run_discovery_cycle(Config.load())
    assert (stored, total) == (1, 2)
    store = DeviceStore(Config.load().db_path())
    try:
        assert store.count() == 1
    finally:
        store.close()
