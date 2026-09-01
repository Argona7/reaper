from __future__ import annotations

from pathlib import Path

import pytest

from reaper.config import ReaperConfig
from reaper.domain import ActionStatus, ActionVerb, ProposedAction, RiskLevel
from reaper.engine import ReaperEngine, load_inputs
from reaper.reporting import build_daily_report, format_telegram, project_zero_date
from reaper.scheduler import run_nightly_report


def test_engine_runs_six_skills(config: ReaperConfig) -> None:
    workspace = Path(__file__).resolve().parents[1]
    engine = ReaperEngine(config, workspace)
    results = engine.run_skills()
    assert len(results) == 6
    assert len(engine.db.list_actions(ActionStatus.PROPOSED)) == 3


def test_engine_blocks_unapproved_execution(config: ReaperConfig) -> None:
    workspace = Path(__file__).resolve().parents[1]
    engine = ReaperEngine(config, workspace)
    saved = engine.db.add_action(
        ProposedAction(
            skill="test",
            verb=ActionVerb.SEND_EMAIL,
            title="Email",
            risk=RiskLevel.HIGH,
            payload={"to": "a@example.com", "subject": "Test", "body": "Body"},
        )
    )
    with pytest.raises(PermissionError):
        engine.execute(saved.id)


def test_engine_records_connector_failure(config: ReaperConfig) -> None:
    workspace = Path(__file__).resolve().parents[1]
    engine = ReaperEngine(config, workspace)
    saved = engine.db.add_action(
        ProposedAction(
            skill="test",
            verb=ActionVerb.SEND_EMAIL,
            title="Email",
            risk=RiskLevel.HIGH,
            payload={"to": "a@example.com", "subject": "Test", "body": "Body"},
            status=ActionStatus.APPROVED,
        )
    )
    with pytest.raises(RuntimeError, match="disabled"):
        engine.execute(saved.id)
    assert engine.db.get_action(saved.id).status == ActionStatus.FAILED


def test_action_export(config: ReaperConfig, tmp_path: Path) -> None:
    workspace = Path(__file__).resolve().parents[1]
    engine = ReaperEngine(config, workspace)
    saved = engine.db.add_action(
        ProposedAction(
            skill="test",
            verb=ActionVerb.TRANSFER_BALANCE,
            title="Transfer",
            risk=RiskLevel.CRITICAL,
            payload={"amount_cents": 610_000},
        )
    )
    target = engine.export_action(saved.id, tmp_path / "action.json")
    assert '"amount_cents": 610000' in target.read_text()


def test_load_inputs_merges_lists(tmp_path: Path) -> None:
    first = tmp_path / "first.yaml"
    second = tmp_path / "second.json"
    first.write_text("assets:\n  - name: one\n")
    second.write_text('{"assets": [{"name": "two"}]}')
    assert [item["name"] for item in load_inputs(first, second)["assets"]] == ["one", "two"]


def test_report_contains_verified_snapshot(config: ReaperConfig) -> None:
    workspace = Path(__file__).resolve().parents[1]
    engine = ReaperEngine(config, workspace)
    report = build_daily_report(config, engine.db, freed_today_cents=3100)
    text = format_telegram(report)
    assert report.debt_balance_cents == 791_200
    assert report.principal_reduced_cents == 48_800
    assert "freed today: $31.00" in text
    assert engine.db.latest_snapshot() is not None


def test_project_zero_date_handles_zero_velocity() -> None:
    assert project_zero_date(100_000, 0) is None
    assert project_zero_date(0, 0) is not None


def test_nightly_report_records_local_event(config: ReaperConfig) -> None:
    workspace = Path(__file__).resolve().parents[1]
    engine = ReaperEngine(config, workspace)
    text = run_nightly_report(config, engine.db)
    assert "Reaper daily report" in text
