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
