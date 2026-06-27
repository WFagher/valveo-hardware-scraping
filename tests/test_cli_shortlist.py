from __future__ import annotations

from click.testing import CliRunner

import engine.cli as cli
from engine.config import Config
from engine.models import ApiType, Controller, Programmability, RebrandPath
from engine.store import DeviceStore


def _seed():
    store = DeviceStore(Config.load().db_path())
    try:
        good = Controller(
            vendor="Milesight",
            model="UC300-L05EU",
            cellular=True,
            api_type=ApiType.native_mqtt,
            programmability=Programmability.rules_engine,
            rebrand_path=RebrandPath.oem_program,
        )
        good.lock.relay_count = 2
        store.upsert(good)
        store.upsert(Controller(vendor="FailCo", model="NoCell", cellular=False))
    finally:
        store.close()


def test_shortlist_shows_passing_only(monkeypatch, tmp_path):
    monkeypatch.setenv("ENGINE_DATA_DIR", str(tmp_path / "data"))
    _seed()
    result = CliRunner().invoke(cli.main, ["shortlist"])
    assert result.exit_code == 0
    assert "Milesight" in result.output
    assert "FailCo" not in result.output


def test_matrix_lists_all(monkeypatch, tmp_path):
    monkeypatch.setenv("ENGINE_DATA_DIR", str(tmp_path / "data"))
    _seed()
    result = CliRunner().invoke(cli.main, ["matrix"])
    assert result.exit_code == 0
    assert "Milesight" in result.output and "FailCo" in result.output
