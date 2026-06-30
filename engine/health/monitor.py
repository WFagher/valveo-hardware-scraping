"""System health monitor for the door-hardware-sourcing-engine.

Reads CPU load, memory pressure, and CPU temperature (macOS), then provides a
HealthGate that the 24/7 scheduler consults before each heavy cycle — so a
machine running continuous LLM inference never cooks itself.

Temperature sources (tried in order, first success wins):
  1. ``osx-cpu-temp`` binary — install with: brew install osx-cpu-temp (Intel)
  2. ``ioreg`` — Apple Silicon die temperature (no sudo)
  3. ``powermetrics`` — one-shot SMC sample (macOS 12+, no sudo)
  4. ``psutil.sensors_temperatures()`` — some Intel Macs
  5. None — temperature-agnostic mode; gate relies on CPU% + memory

Gate states:  OK → run · WARM → wait with back-off · HOT → skip this cycle.
"""
from __future__ import annotations

import io
import logging
import plistlib
import re
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

log = logging.getLogger("engine.health")

try:
    import psutil as _psutil

    _PSUTIL_OK = True
except ImportError:  # pragma: no cover
    _psutil = None
    _PSUTIL_OK = False
    log.warning("psutil not installed — health monitoring disabled.")


@dataclass
class HealthThresholds:
    """Tunable limits. Conservative defaults for a Mac under sustained load."""

    cpu_warn: float = 72.0
    cpu_block: float = 90.0
    mem_warn: float = 82.0
    mem_block: float = 95.0
    temp_warn: float = 78.0
    temp_block: float = 88.0

    poll_interval_secs: int = 20
    wait_timeout_secs: int = 300
    cooldown_secs: int = 60


class GateStatus(Enum):
    OK = "ok"
    WARM = "warm"
    HOT = "hot"


def _classify(cpu: float, mem: float, temp: float | None, t: HealthThresholds) -> GateStatus:
    if cpu >= t.cpu_block or mem >= t.mem_block or (temp is not None and temp >= t.temp_block):
        return GateStatus.HOT
    if cpu >= t.cpu_warn or mem >= t.mem_warn or (temp is not None and temp >= t.temp_warn):
        return GateStatus.WARM
    return GateStatus.OK


@dataclass
class HealthSnapshot:
    """Point-in-time reading of all health metrics."""

    cpu_percent: float
    memory_percent: float
    cpu_temp: float | None
    cpu_freq_mhz: float | None
    cpu_freq_max_mhz: float | None
    timestamp: str = field(
        default_factory=lambda: datetime.now().isoformat(timespec="seconds")
    )

    @property
    def gate_status(self) -> GateStatus:
        return _classify(self.cpu_percent, self.memory_percent, self.cpu_temp, HealthThresholds())

    @property
    def status_emoji(self) -> str:
        return {GateStatus.OK: "🟢", GateStatus.WARM: "🟡", GateStatus.HOT: "🔴"}[self.gate_status]

    def summary_line(self) -> str:
        parts = [f"CPU {self.cpu_percent:5.1f}%", f"mem {self.memory_percent:5.1f}%"]
        if self.cpu_temp is not None:
            parts.append(f"temp {self.cpu_temp:4.1f} °C")
        if self.cpu_freq_mhz is not None and self.cpu_freq_max_mhz is not None:
            parts.append(
                f"freq {self.cpu_freq_mhz / 1000:.2f}/{self.cpu_freq_max_mhz / 1000:.2f} GHz"
            )
        parts.append(self.status_emoji)
        return "  ".join(parts)


# --- temperature readers (first non-None > 5°C wins) ---


def _read_temp_osx_cpu_temp() -> float | None:
    if not shutil.which("osx-cpu-temp"):
        return None
    try:
        result = subprocess.run(["osx-cpu-temp"], capture_output=True, text=True, timeout=3)
        val = float(result.stdout.strip().replace("°C", "").replace(" ", ""))
        return val if val > 5.0 else None  # 0.0 means sensor unreadable (Apple Silicon)
    except Exception:
        return None


def _read_temp_ioreg() -> float | None:
    try:
        result = subprocess.run(
            ["ioreg", "-r", "-d", "2", "-n", "IOHIDEventSystemClient"],
            capture_output=True, text=True, timeout=5,
        )
        matches = re.findall(
            r'"CPU die temperature"\s*=\s*([0-9]+(?:\.[0-9]+)?)', result.stdout
        )
        if matches:
            return float(matches[0])
    except Exception:
        pass
    return None


def _read_temp_powermetrics() -> float | None:
    try:
        result = subprocess.run(
            ["powermetrics", "-n", "1", "-i", "1", "--samplers", "smc", "--format", "plist"],
            capture_output=True, text=True, timeout=8,
        )
        if result.returncode != 0:
            return None
        data = plistlib.load(io.BytesIO(result.stdout.encode()))
        smc = data.get("smc") or {}
        for key in ("CPU die temperature", "cpu_die_temperature", "CPU_DIE_TEMPERATURE"):
            if key in smc:
                return float(smc[key])
    except Exception:
        pass
    return None


def _read_temp_psutil() -> float | None:
    if not _PSUTIL_OK:
        return None
    try:
        temps = _psutil.sensors_temperatures()
        for key in ("coretemp", "cpu_thermal", "acpitz"):
            if key in temps and temps[key]:
                return max(t.current for t in temps[key])
    except Exception:
        pass
    return None


def _read_temp() -> float | None:
    for reader in (
        _read_temp_osx_cpu_temp,
        _read_temp_ioreg,
        _read_temp_powermetrics,
        _read_temp_psutil,
    ):
        val = reader()
        if val is not None:
            return val
    return None


class SystemHealth:
    """Thin wrapper around psutil + macOS temperature sources."""

    def snapshot(self) -> HealthSnapshot:
        cpu = _psutil.cpu_percent(interval=0.5) if _PSUTIL_OK else 0.0
        mem = _psutil.virtual_memory().percent if _PSUTIL_OK else 0.0
        freq_cur, freq_max = None, None
        if _PSUTIL_OK:
            try:
                freq = _psutil.cpu_freq()
                if freq is not None:
                    freq_cur, freq_max = freq.current, (freq.max or None)
            except Exception:
                pass
        return HealthSnapshot(
            cpu_percent=cpu,
            memory_percent=mem,
            cpu_temp=_read_temp(),
            cpu_freq_mhz=freq_cur,
            cpu_freq_max_mhz=freq_max,
        )


class CooldownTracker:
    """Minimum rest period between consecutive heavy jobs."""

    def __init__(self, min_gap_secs: int = 60) -> None:
        self._min_gap = min_gap_secs
        self._last_completed = 0.0
        self._lock = threading.Lock()

    def wait_for_cooldown(self) -> None:
        while True:
            with self._lock:
                remaining = self._min_gap - (time.monotonic() - self._last_completed)
            if remaining <= 0:
                return
            time.sleep(min(remaining, 10))

    def mark_completed(self) -> None:
        with self._lock:
            self._last_completed = time.monotonic()


class HealthGate:
    """Gate heavy LLM cycles on live system health."""

    def __init__(self, thresholds: HealthThresholds | None = None) -> None:
        self.thresholds = thresholds or HealthThresholds()
        self.health = SystemHealth()
        self.cooldown = CooldownTracker(min_gap_secs=self.thresholds.cooldown_secs)

    def current_status(self) -> tuple[GateStatus, HealthSnapshot]:
        snap = self.health.snapshot()
        return self._evaluate(snap), snap

    def _evaluate(self, snap: HealthSnapshot) -> GateStatus:
        return _classify(snap.cpu_percent, snap.memory_percent, snap.cpu_temp, self.thresholds)

    def should_skip(self) -> bool:
        """Non-blocking: True if currently HOT."""
        return self.current_status()[0] == GateStatus.HOT

    def wait_until_ok(self, job_name: str = "cycle") -> bool:
        """Block until OK or timeout. True = safe to run, False = skip the job."""
        self.cooldown.wait_for_cooldown()
        deadline = time.monotonic() + self.thresholds.wait_timeout_secs
        warned = False
        while time.monotonic() < deadline:
            status, snap = self.current_status()
            if status == GateStatus.OK:
                return True
            if not warned:
                log.warning("[health] %s waiting — %s", job_name, snap.summary_line())
                warned = True
            time.sleep(self.thresholds.poll_interval_secs)
        _, snap = self.current_status()
        log.error("[health] %s skipped — still hot: %s", job_name, snap.summary_line())
        return False
