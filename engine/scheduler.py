"""APScheduler daemon: continuous full discovery+enrich+report cycle, 24/7."""
from __future__ import annotations

import logging
import os
import sys
from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger
from rich.console import Console

from .config import Config
from .health.monitor import HealthGate
from .pipeline import run_full_cycle

console = Console()
_gate = HealthGate()


def _cycle_minutes() -> int:
    try:
        return max(1, int(os.environ.get("ENGINE_CYCLE_MINUTES", "30")))
    except ValueError:
        return 30


def _cycle_job(cfg: Config) -> None:
    status, snap = _gate.current_status()
    console.print(f"[health] {snap.summary_line()}")
    # Pause / skip the cycle if the machine is hot — protects 24/7 operation.
    if not _gate.wait_until_ok("cycle"):
        console.print("[cycle] skipped — machine too hot")
        return
    try:
        ts = datetime.now().isoformat(timespec="minutes")
        result = run_full_cycle(cfg, timestamp=ts)
        console.print(
            f"[cycle {ts}] prospected {result['prospected']} · "
            f"discovered {result['discovered']} · enriched {result['enriched']} "
            f"→ {result['report']}"
        )
    except Exception as exc:  # a bad cycle must never kill the daemon
        console.print(f"[cycle] error: {exc}")
    finally:
        _gate.cooldown.mark_completed()


def build_scheduler(cfg: Config) -> BlockingScheduler:
    sched = BlockingScheduler(timezone="Europe/Stockholm")
    sched.add_job(
        _cycle_job,
        IntervalTrigger(minutes=_cycle_minutes()),
        args=[cfg],
        id="full-cycle",
        name="Full discovery+enrich+report cycle",
        max_instances=1,
        coalesce=True,
    )
    return sched


def start() -> None:
    # Stream the log live even when redirected to a file (nohup block-buffers otherwise).
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass
    # Surface health-gate warnings (waiting / skipping when hot) in the log.
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    cfg = Config.load()
    console.print(
        f"[bold]engine scheduler[/bold] — full cycle every {_cycle_minutes()} min, 24/7. "
        "Ctrl+C to stop."
    )
    _cycle_job(cfg)  # run one cycle immediately for instant feedback
    sched = build_scheduler(cfg)
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        console.print("stopped.")
