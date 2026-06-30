from __future__ import annotations

from engine.health.monitor import GateStatus, HealthGate, HealthSnapshot


def _snap(cpu, mem, temp=None):
    return HealthSnapshot(
        cpu_percent=cpu, memory_percent=mem, cpu_temp=temp,
        cpu_freq_mhz=None, cpu_freq_max_mhz=None,
    )


def test_gate_status_ok():
    assert _snap(10, 20).gate_status is GateStatus.OK


def test_gate_status_warm_on_cpu():
    assert _snap(75, 20).gate_status is GateStatus.WARM  # cpu_warn 72


def test_gate_status_hot_on_cpu():
    assert _snap(95, 20).gate_status is GateStatus.HOT  # cpu_block 90


def test_gate_status_hot_on_memory():
    assert _snap(10, 96).gate_status is GateStatus.HOT  # mem_block 95


def test_gate_status_temperature_thresholds():
    assert _snap(10, 20, temp=80).gate_status is GateStatus.WARM  # temp_warn 78
    assert _snap(10, 20, temp=90).gate_status is GateStatus.HOT  # temp_block 88
    assert _snap(10, 20, temp=50).gate_status is GateStatus.OK


def test_summary_line_includes_metrics():
    line = _snap(42.0, 58.0, temp=70.0).summary_line()
    assert "CPU" in line and "mem" in line and "70.0" in line


def test_should_skip_when_hot(monkeypatch):
    gate = HealthGate()
    monkeypatch.setattr(gate.health, "snapshot", lambda: _snap(99, 20))
    assert gate.should_skip() is True
    monkeypatch.setattr(gate.health, "snapshot", lambda: _snap(5, 20))
    assert gate.should_skip() is False
