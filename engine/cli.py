"""`engine` CLI entry point."""
from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from .config import Config
from .crawlers.fetcher import fetch_text
from .extractors.spec_extractor import extract_controller
from .llm.ollama_client import OllamaClient
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


@main.command()
def ping() -> None:
    """Check the Ollama chat model responds."""
    cfg = Config.load()
    with OllamaClient(cfg.ollama_host) as ol:
        ok = ol.ping(cfg.chat_model)
    state = "[green]OK[/green]" if ok else "[red]no response[/red]"
    console.print(f"Ollama {cfg.chat_model}: {state}")


def _read_target(target: str) -> str:
    p = Path(target)
    if p.is_file():
        return p.read_text()
    return fetch_text(target)


@main.command()
@click.argument("target")
def extract(target: str) -> None:
    """Extract one controller from a file path or URL and store it."""
    cfg = Config.load()
    text = _read_target(target)
    with OllamaClient(cfg.ollama_host) as ol:
        controller = extract_controller(text, ollama=ol, model=cfg.chat_model, source_url=target)
    if controller is None:
        console.print("[yellow]No controller extracted.[/yellow]")
        return
    store = DeviceStore(cfg.db_path())
    try:
        store.upsert(controller)
    finally:
        store.close()
    console.print(f"[green]Stored:[/green] {controller.vendor} {controller.model}")


@main.command()
def discover() -> None:
    """Extract controllers from every URL in config/seed_urls.yaml."""
    import yaml

    cfg = Config.load()
    urls = yaml.safe_load((cfg.config_dir / "seed_urls.yaml").read_text())["urls"]
    store = DeviceStore(cfg.db_path())
    stored = 0
    try:
        with OllamaClient(cfg.ollama_host) as ol:
            for url in urls:
                text = fetch_text(url)
                controller = extract_controller(
                    text, ollama=ol, model=cfg.chat_model, source_url=url
                )
                if controller is not None:
                    store.upsert(controller)
                    stored += 1
                    console.print(f"  [green]+[/green] {controller.vendor} {controller.model}")
                else:
                    console.print(f"  [yellow]-[/yellow] {url}")
    finally:
        store.close()
    console.print(f"Discovered {stored}/{len(urls)} controllers.")


if __name__ == "__main__":
    main()
