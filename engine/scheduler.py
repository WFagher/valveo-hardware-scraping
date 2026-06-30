"""APScheduler daemon: continuous full discovery+enrich+report cycle, 24/7."""
from __future__ import annotations

import os
from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger
from rich.console import Console

from .config import Config
from .pipeline import run_full_cycle

console = Console()


def _cycle_minutes() -> int:
    try:
        return max(1, int(os.environ.get("ENGINE_CYCLE_MINUTES", "30")))
    except ValueError:
        return 30


def _cycle_job(cfg: Config) -> None:
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
