"""`engine` CLI entry point."""
from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from .compare.shortlist import build_shortlist
from .config import Config
from .crawlers.fetcher import fetch_text
from .drafters.deep_dive import generate_deep_dive
from .extractors.spec_extractor import extract_controller
from .llm.ollama_client import OllamaClient
from .research_config import load_requirements, load_scoring
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


@main.command()
def matrix() -> None:
    """Print a spec matrix of every stored controller."""
    cfg = Config.load()
    store = DeviceStore(cfg.db_path())
    try:
        controllers = store.all()
    finally:
        store.close()
    table = Table()
    for col in ("Vendor", "Model", "Cellular", "API", "Relays", "WiFi", "BLE"):
        table.add_column(col)
    for c in controllers:
        table.add_row(
            c.vendor, c.model, str(c.cellular), c.api_type.value,
            str(c.lock.relay_count), str(c.wifi), str(c.bluetooth),
        )
    console.print(table)


@main.command()
@click.option("--top", default=10, help="Max items per segment.")
def shortlist(top: int) -> None:
    """Ranked shortlist, grouped by reader-capable vs relay-only."""
    cfg = Config.load()
    req = load_requirements(cfg.config_dir)
    weights = load_scoring(cfg.config_dir)["weights"]
    store = DeviceStore(cfg.db_path())
    try:
        controllers = store.all()
    finally:
        store.close()
    ranked = build_shortlist(controllers, req, weights)
    if not ranked:
        console.print("[yellow]No controllers pass the hard criteria yet.[/yellow]")
        return
    for seg in ("reader-capable", "relay-only"):
        items = [s for s in ranked if s.segment == seg][:top]
        if not items:
            continue
        console.print(f"[bold]{seg}[/bold]")
        for i, s in enumerate(items, 1):
            tags = " ".join(s.tags)
            console.print(
                f"  {i}. {s.controller.vendor} {s.controller.model} "
                f"— {s.score * 10:.1f}/10  {tags}"
            )


@main.command(name="deep-dive")
@click.argument("key")
@click.option("--stdout", "to_stdout", is_flag=True, help="Print instead of writing a file.")
def deep_dive(key: str, to_stdout: bool) -> None:
    """Generate the per-device deep-dive report for a controller KEY."""
    cfg = Config.load()
    store = DeviceStore(cfg.db_path())
    try:
        controller = store.get(key)
    finally:
        store.close()
    if controller is None:
        console.print(f"[yellow]Controller not found:[/yellow] {key}")
        return
    req = load_requirements(cfg.config_dir)
    with OllamaClient(cfg.ollama_host) as ol:
        md = generate_deep_dive(controller, req, ollama=ol, model=cfg.chat_model)
    if to_stdout:
        console.print(md)
        return
    reports = cfg.data_dir.parent / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    safe = key.replace("::", "__").replace("/", "_")
    out = reports / f"{safe}.md"
    out.write_text(md)
    console.print(f"[green]Wrote[/green] {out}")


if __name__ == "__main__":
    main()
