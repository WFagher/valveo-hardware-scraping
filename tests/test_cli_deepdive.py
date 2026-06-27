from __future__ import annotations

from click.testing import CliRunner

import engine.cli as cli
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


def _store_uc300():
    store = DeviceStore(Config.load().db_path())
    try:
        store.upsert(Controller(vendor="Milesight", model="UC300-L05EU", cellular=True))
    finally:
        store.close()


def test_deep_dive_stdout(monkeypatch, tmp_path):
    monkeypatch.setenv("ENGINE_DATA_DIR", str(tmp_path / "data"))
    _store_uc300()
    monkeypatch.setattr(cli, "OllamaClient", _DummyOllama)
    monkeypatch.setattr(cli, "generate_deep_dive", lambda c, req, **kw: f"# {c.vendor} deep dive")
    result = CliRunner().invoke(cli.main, ["deep-dive", "milesight::uc300-l05eu", "--stdout"])
    assert result.exit_code == 0
    assert "Milesight deep dive" in result.output


def test_deep_dive_unknown_key(monkeypatch, tmp_path):
    monkeypatch.setenv("ENGINE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(cli, "OllamaClient", _DummyOllama)
    result = CliRunner().invoke(cli.main, ["deep-dive", "nope::nope"])
    assert result.exit_code == 0
    assert "not found" in result.output.lower()
