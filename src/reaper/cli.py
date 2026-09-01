from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Annotated

import typer
import uvicorn
import yaml
from rich.console import Console
from rich.table import Table

from reaper import __version__
from reaper.api import create_app
from reaper.config import ReaperConfig, load_config
from reaper.connectors.gmail import GmailConnector
from reaper.connectors.telegram import TelegramConnector
from reaper.db import ReaperDB
from reaper.domain import ActionStatus
from reaper.engine import ReaperEngine, load_inputs
from reaper.parsers import CSVStatementParser, OFXStatementParser, PDFStatementParser
from reaper.parsers.base import StatementParser
from reaper.reporting import build_daily_report, format_telegram
from reaper.scheduler import run_scheduler

app = typer.Typer(
    name="reaper",
    no_args_is_help=True,
    help="Open-source debt operations agent.",
)
console = Console()


def _workspace() -> Path:
    source_root = Path(__file__).resolve().parents[2]
    if (source_root / "playbooks").is_dir():
        return source_root
    package_root = Path(__file__).resolve().parent
    if (package_root / "playbooks").is_dir():
        return package_root
    raise RuntimeError("Reaper playbooks are missing from the installation")


def _engine(config_path: Path) -> ReaperEngine:
    return ReaperEngine(load_config(config_path), _workspace())


@app.command()
def version() -> None:
    """Print the installed Reaper version."""
    console.print(__version__)


@app.command()
def init(
    destination: Annotated[Path, typer.Option("--destination", "-d")] = Path("reaper.yaml"),
    force: Annotated[bool, typer.Option(help="Replace an existing configuration file.")] = False,
) -> None:
    """Create a local configuration and private runtime directory."""
    destination = destination.resolve()
    if destination.exists() and not force:
        raise typer.BadParameter(f"{destination} already exists; pass --force to replace it")
    source = _workspace() / "reaper.yaml.example"
    shutil.copyfile(source, destination)
    data = yaml.safe_load(destination.read_text())
    runtime = destination.parent / data["agent"]["database"]
    runtime.parent.mkdir(parents=True, exist_ok=True)
    db = ReaperDB(runtime)
    db.migrate()
    console.print(f"[green]initialized[/green] {destination}")
    console.print(f"database: {runtime}")


@app.command("import")
def import_statement(
    path: Annotated[Path, typer.Argument(exists=True, readable=True)],
    config: Annotated[Path, typer.Option("--config", "-c")] = Path("reaper.yaml"),
    account_last4: Annotated[str, typer.Option(help="Card account suffix.")] = "",
) -> None:
    """Import a CSV, OFX/QFX, or text-based PDF statement."""
    suffix = path.suffix.lower()
    parser: StatementParser
    if suffix == ".csv":
        parser = CSVStatementParser()
    elif suffix in {".ofx", ".qfx"}:
        parser = OFXStatementParser()
    elif suffix == ".pdf":
        parser = PDFStatementParser()
    else:
        raise typer.BadParameter("Supported statement formats: .csv, .ofx, .qfx, .pdf")
    service = _engine(config)
    transactions = parser.parse(
        path, account_last4=account_last4 or service.config.debt.account_last4
    )
    inserted = service.db.add_transactions(transactions)
    service.db.append_event(
        "statement.imported",
        {"path": str(path.resolve()), "parsed": len(transactions), "inserted": inserted},
    )
    console.print(f"[green]imported[/green] {inserted}/{len(transactions)} transactions")


@app.command("run")
def run_agent(
    config: Annotated[Path, typer.Option("--config", "-c")] = Path("reaper.yaml"),
    inputs: Annotated[
        list[Path] | None,
        typer.Option("--inputs", "-i", help="YAML/JSON files with offers or selected assets."),
    ] = None,
) -> None:
    """Run all six skills and persist opportunities and approval requests."""
    service = _engine(config)
    payload = load_inputs(*(inputs or []))
    results = service.run_skills(payload)
    table = Table(title=f"{service.config.agent.name} run")
    table.add_column("skill")
    table.add_column("opportunities", justify="right")
    table.add_column("actions", justify="right")
    table.add_column("result")
    for result in results:
        table.add_row(
            result.skill,
            str(len(result.opportunities)),
            str(len(result.actions)),
            " ".join(result.notes),
        )
    console.print(table)


@app.command()
def actions(
    config: Annotated[Path, typer.Option("--config", "-c")] = Path("reaper.yaml"),
    status: Annotated[ActionStatus | None, typer.Option()] = None,
) -> None:
    """List action packages and their approval state."""
    service = _engine(config)
    rows = service.db.list_actions(status)
    table = Table(title="Reaper actions")
    for column in ("id", "status", "verb", "risk", "title"):
        table.add_column(column)
    for action in rows:
        table.add_row(
            action.id[:8],
            action.status.value,
            action.verb.value,
            action.risk.value,
            action.title,
        )
    console.print(table)


@app.command()
def approve(
    action_id: str,
    config: Annotated[Path, typer.Option("--config", "-c")] = Path("reaper.yaml"),
    actor: Annotated[str, typer.Option()] = "operator",
    reason: Annotated[str | None, typer.Option()] = None,
) -> None:
    """Approve one exact action payload."""
    action = _engine(config).approve(action_id, actor=actor, reason=reason)
    console.print(f"[green]approved[/green] {action.id} {action.title}")


@app.command()
def reject(
    action_id: str,
    config: Annotated[Path, typer.Option("--config", "-c")] = Path("reaper.yaml"),
    actor: Annotated[str, typer.Option()] = "operator",
    reason: Annotated[str | None, typer.Option()] = None,
) -> None:
    """Reject one exact action payload."""
    action = _engine(config).reject(action_id, actor=actor, reason=reason)
    console.print(f"[yellow]rejected[/yellow] {action.id} {action.title}")


@app.command()
def execute(
    action_id: str,
    config: Annotated[Path, typer.Option("--config", "-c")] = Path("reaper.yaml"),
) -> None:
    """Execute an approved action through its configured connector."""
    result = _engine(config).execute(action_id)
    console.print_json(json.dumps(result))


@app.command("export-action")
def export_action(
    action_id: str,
    destination: Path,
    config: Annotated[Path, typer.Option("--config", "-c")] = Path("reaper.yaml"),
) -> None:
    """Export an action package for an issuer or merchant channel."""
    target = _engine(config).export_action(action_id, destination)
    console.print(f"[green]exported[/green] {target.resolve()}")


@app.command()
def report(
    config: Annotated[Path, typer.Option("--config", "-c")] = Path("reaper.yaml"),
    freed_today: Annotated[float, typer.Option(help="Verified dollars freed today.")] = 0.0,
    send: Annotated[bool, typer.Option(help="Send through the configured Telegram bot.")] = False,
) -> None:
    """Generate the 21:00 debt report; optionally send it to Telegram."""
    service = _engine(config)
    daily = build_daily_report(
        service.config,
        service.db,
        freed_today_cents=round(freed_today * 100),
    )
    text = format_telegram(daily, service.config.agent.name)
    console.print(text)
    if send:
        if not service.config.connectors.telegram.enabled:
            raise typer.BadParameter("Telegram connector is disabled in reaper.yaml")
        result = TelegramConnector().send(text)
        service.db.append_event("report.telegram.sent", result)
        console.print(f"[green]sent[/green] message {result['message_id']}")


@app.command()
def schedule(
    config: Annotated[Path, typer.Option("--config", "-c")] = Path("reaper.yaml"),
) -> None:
    """Run the persistent nightly scheduler."""
    resolved = load_config(config)
    db = ReaperDB(resolved.agent.database)
    db.migrate()
    console.print(
        f"scheduler running: {resolved.owner.report_hour:02d}:00 {resolved.owner.timezone}"
    )
    run_scheduler(resolved, db)


@app.command()
def serve(
    config: Annotated[Path, typer.Option("--config", "-c")] = Path("reaper.yaml"),
    host: Annotated[str, typer.Option()] = "127.0.0.1",
    port: Annotated[int, typer.Option()] = 8787,
) -> None:
    """Start the local API and approval console."""
    api = create_app(load_config(config), _workspace())
    uvicorn.run(api, host=host, port=port)


@app.command("gmail-auth")
def gmail_auth(
    config: Annotated[Path, typer.Option("--config", "-c")] = Path("reaper.yaml"),
    client_secret_file: Annotated[Path | None, typer.Option()] = None,
) -> None:
    """Authorize Gmail locally and store the OAuth token with mode 0600."""
    resolved = load_config(config)
    connector = GmailConnector(
        token_file=resolved.connectors.gmail.token_file,
        sender=resolved.connectors.gmail.sender,
    )
    connector.authenticate(client_secret_file)
    console.print(f"[green]authorized[/green] {resolved.connectors.gmail.token_file}")


@app.command()
def doctor(
    config: Annotated[Path, typer.Option("--config", "-c")] = Path("reaper.yaml"),
) -> None:
    """Validate configuration, playbooks, database, and connector prerequisites."""
    resolved: ReaperConfig = load_config(config)
    db = ReaperDB(resolved.agent.database)
    db.migrate()
    checks = {
        "config": True,
        "database": resolved.agent.database.exists(),
        "six skills": len(list((_workspace() / "playbooks" / "skills").glob("*.yaml"))) == 6,
        "APR playbook": len(list((_workspace() / "playbooks" / "apr-retention").glob("*.md"))) == 3,
        "Gmail token": (
            not resolved.connectors.gmail.enabled or resolved.connectors.gmail.token_file.exists()
        ),
    }
    for name, ok in checks.items():
        console.print(f"{'[green]ok[/green]' if ok else '[red]fail[/red]'} {name}")
    if not all(checks.values()):
        raise typer.Exit(1)
