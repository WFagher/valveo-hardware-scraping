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

    def chat(self, *a, **k):
        return "{}"


def test_extract_from_file_upserts(monkeypatch, tmp_path):
    monkeypatch.setenv("ENGINE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(cli, "OllamaClient", _DummyOllama)
    monkeypatch.setattr(
        cli,
        "extract_controller",
        lambda text, **kw: Controller(vendor="Milesight", model="UC300-L05EU", cellular=True),
    )
    src = tmp_path / "uc300.txt"
    src.write_text("Milesight UC300 4G LTE MQTT")
    result = CliRunner().invoke(cli.main, ["extract", str(src)])
    assert result.exit_code == 0
    assert "Milesight" in result.output

    store = DeviceStore(Config.load().db_path())
    try:
        assert store.count() == 1
    finally:
        store.close()


def test_extract_handles_no_record(monkeypatch, tmp_path):
    monkeypatch.setenv("ENGINE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(cli, "OllamaClient", _DummyOllama)
    monkeypatch.setattr(cli, "extract_controller", lambda text, **kw: None)
    src = tmp_path / "empty.txt"
    src.write_text("nothing useful")
    result = CliRunner().invoke(cli.main, ["extract", str(src)])
    assert result.exit_code == 0
    assert "No controller" in result.output
