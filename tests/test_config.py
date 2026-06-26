from __future__ import annotations

from engine.config import Config


def test_load_defaults(monkeypatch, tmp_path):
    for var in ("OLLAMA_HOST", "OLLAMA_CHAT_MODEL", "ENGINE_DATA_DIR", "ENGINE_CONFIG_DIR"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("ENGINE_DATA_DIR", str(tmp_path / "data"))
    cfg = Config.load()
    assert cfg.ollama_host == "http://localhost:11434"
    assert cfg.chat_model.startswith("llama3.3")
    assert cfg.db_path() == (tmp_path / "data" / "devices.sqlite3").resolve()
    assert cfg.db_path().parent.is_dir()  # db_path() creates data_dir
