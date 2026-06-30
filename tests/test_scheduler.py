from __future__ import annotations

from engine.config import Config
from engine.scheduler import build_scheduler


def test_build_scheduler_registers_full_cycle_job(monkeypatch, tmp_path):
    monkeypatch.setenv("ENGINE_DATA_DIR", str(tmp_path / "data"))
    sched = build_scheduler(Config.load())
    job_ids = {j.id for j in sched.get_jobs()}
    assert "full-cycle" in job_ids
