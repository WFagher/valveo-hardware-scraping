from __future__ import annotations

from click.testing import CliRunner

from engine.cli import main


def test_paths_runs(monkeypatch, tmp_path):
    monkeypatch.setenv("ENGINE_DATA_DIR", str(tmp_path / "data"))
    result = CliRunner().invoke(main, ["paths"])
    assert result.exit_code == 0
    assert "Ollama host" in result.output


def test_requirements_shows_benchmark():
    result = CliRunner().invoke(main, ["requirements"])
    assert result.exit_code == 0
    assert "UC300-L05EU" in result.output


def test_db_info_reports_count(monkeypatch, tmp_path):
    monkeypatch.setenv("ENGINE_DATA_DIR", str(tmp_path / "data"))
    result = CliRunner().invoke(main, ["db-info"])
    assert result.exit_code == 0
    assert "0" in result.output
