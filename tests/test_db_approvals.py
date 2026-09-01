from __future__ import annotations

from pathlib import Path

import pytest

from reaper.approvals import ApprovalPolicy
from reaper.config import ReaperConfig
from reaper.db import ReaperDB
from reaper.domain import (
    ActionStatus,
    ActionVerb,
    ApprovalRecord,
    ProposedAction,
    RiskLevel,
    Transaction,
)


def action(verb: ActionVerb = ActionVerb.SEND_EMAIL) -> ProposedAction:
    return ProposedAction(
        skill="test",
        verb=verb,
        title="Test action",
        risk=RiskLevel.HIGH,
        payload={"value": 1},
    )


def test_database_deduplicates_transactions(tmp_path: Path) -> None:
    db = ReaperDB(tmp_path / "db.sqlite3")
    db.migrate()
    transaction = Transaction(posted_at="2026-01-01", description="Coffee", amount_cents=425)
    assert db.add_transactions([transaction]) == 1
    assert db.add_transactions([transaction]) == 0
    assert len(db.list_transactions()) == 1


def test_database_preserves_distinct_issuer_transaction_ids(tmp_path: Path) -> None:
    db = ReaperDB(tmp_path / "db.sqlite3")
    db.migrate()
    first = Transaction(
        posted_at="2026-01-01",
        description="Camera Shop",
        amount_cents=11_800,
        source_id="issuer-1",
    )
    second = first.model_copy(update={"source_id": "issuer-2"})
    assert db.add_transactions([first, second]) == 2
    assert len(db.list_transactions()) == 2


def test_database_deduplicates_actions_by_payload(tmp_path: Path) -> None:
    db = ReaperDB(tmp_path / "db.sqlite3")
    db.migrate()
    first = db.add_action(action())
    second = db.add_action(action())
    assert first.id == second.id
    assert len(db.list_actions()) == 1


def test_approval_lifecycle(tmp_path: Path) -> None:
    db = ReaperDB(tmp_path / "db.sqlite3")
    db.migrate()
    saved = db.add_action(action())
    approved = db.decide_action(
        ApprovalRecord(
            action_id=saved.id,
            decision=ActionStatus.APPROVED,
            actor="operator",
        )
    )
    assert approved.status == ActionStatus.APPROVED
    with pytest.raises(ValueError, match="already approved"):
        db.decide_action(
            ApprovalRecord(
                action_id=saved.id,
                decision=ActionStatus.REJECTED,
                actor="operator",
            )
        )


def test_policy_requires_side_effect_approval(config: ReaperConfig) -> None:
    policy = ApprovalPolicy(config.approval)
    decision = policy.evaluate(action(ActionVerb.SEND_EMAIL))
    assert decision.requires_approval is True
    assert decision.expires_at is not None


def test_policy_auto_allows_drafts(config: ReaperConfig) -> None:
    policy = ApprovalPolicy(config.approval)
    decision = policy.evaluate(action(ActionVerb.DRAFT))
    assert decision.requires_approval is False
    assert policy.initial_status(action(ActionVerb.DRAFT)) == ActionStatus.APPROVED
