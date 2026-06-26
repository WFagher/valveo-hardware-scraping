"""`engine` CLI entry point."""
from __future__ import annotations

import click
from rich.console import Console
from rich.table import Table

from .config import Config
from .research_config import load_requirements
from .store import DeviceStore

console = Console()


@click.group()
def main() -> None:
    """door-hardware-sourcing-engine."""


@main.command()
def paths() -> None:
    """Print resolved config from .env."""
    cfg = Config.load()
    table = Table(show_header=False, box=None)
    table.add_row("Ollama host", cfg.ollama_host)
    table.add_row("Chat model", cfg.chat_model)
    table.add_row("Data dir", str(cfg.data_dir))
    table.add_row("Config dir", str(cfg.config_dir))
    console.print(table)


@main.command(name="db-info")
def db_info() -> None:
    """Show how many controllers are stored."""
    cfg = Config.load()
    store = DeviceStore(cfg.db_path())
    try:
        console.print(f"Controllers stored: {store.count()}")
    finally:
        store.close()


@main.command()
def requirements() -> None:
    """Print the hard/bonus criteria and the benchmark device."""
    cfg = Config.load()
    req = load_requirements(cfg.config_dir)
    console.print(f"[bold]Benchmark:[/bold] {req['benchmark']}")
    console.print(f"[bold]Hard criteria:[/bold] {req['hard']}")


if __name__ == "__main__":
    main()
