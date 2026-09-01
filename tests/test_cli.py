from __future__ import annotations

from pathlib import Path

import yaml
from typer.testing import CliRunner

from reaper.cli import app
from reaper.config import ReaperConfig

runner = CliRunner()


def write_config(config: ReaperConfig, path: Path) -> None:
    path.write_text(yaml.safe_dump(config.model_dump(mode="json"), sort_keys=False))


def test_cli_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.stdout


def test_cli_init_import_run_report_doctor(config: ReaperConfig, tmp_path: Path) -> None:
    config_path = tmp_path / "reaper.yaml"
    write_config(config, config_path)
    statement = tmp_path / "statement.csv"
    statement.write_text(
        "Date,Description,Amount\n"
        "2026-01-03,NETFLIX,-15.49\n"
        "2026-02-03,NETFLIX,-15.49\n"
        "2026-03-03,NETFLIX,-15.49\n"
    )
    imported = runner.invoke(app, ["import", str(statement), "-c", str(config_path)])
    assert imported.exit_code == 0, imported.stdout
    assert "3/3 transactions" in imported.stdout

    run = runner.invoke(app, ["run", "-c", str(config_path)])
    assert run.exit_code == 0, run.stdout
    assert "apr-negotiation" in run.stdout

    actions = runner.invoke(app, ["actions", "-c", str(config_path)])
    assert actions.exit_code == 0
    assert "send_email" in actions.stdout

    report = runner.invoke(app, ["report", "-c", str(config_path), "--freed-today", "31"])
    assert report.exit_code == 0
    assert "freed today: $31.00" in report.stdout

    doctor = runner.invoke(app, ["doctor", "-c", str(config_path)])
    assert doctor.exit_code == 0
    assert "six skills" in doctor.stdout


def test_cli_init_creates_config(tmp_path: Path) -> None:
    target = tmp_path / "new-reaper.yaml"
    result = runner.invoke(app, ["init", "-d", str(target)])
    assert result.exit_code == 0, result.stdout
    assert target.exists()
    duplicate = runner.invoke(app, ["init", "-d", str(target)])
    assert duplicate.exit_code != 0
