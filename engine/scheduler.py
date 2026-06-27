"""APScheduler daemon: periodic discovery re-crawl."""
from __future__ import annotations

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from rich.console import Console

from .config import Config
from .pipeline import run_discovery_cycle

console = Console()


def _discovery_job(cfg: Config) -> None:
    stored, total = run_discovery_cycle(cfg)
    console.print(f"[discovery] stored {stored}/{total}")


def build_scheduler(cfg: Config) -> BlockingScheduler:
    sched = BlockingScheduler(timezone="Europe/Stockholm")
    sched.add_job(
        _discovery_job,
        CronTrigger(hour=4, minute=0),
        args=[cfg],
        id="daily-discovery",
        name="Daily discovery re-crawl",
    )
    return sched


def start() -> None:
    cfg = Config.load()
    sched = build_scheduler(cfg)
    console.print(
        "[bold]engine scheduler[/bold] — daily discovery 04:00 Europe/Stockholm. Ctrl+C to stop."
    )
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        console.print("stopped.")
