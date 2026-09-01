from __future__ import annotations

from datetime import date
from pathlib import Path

from reaper.config import ReaperConfig
from reaper.db import ReaperDB
from reaper.domain import ActionVerb, Transaction
from reaper.skills.apr_negotiation import APRNegotiationSkill
from reaper.skills.asset_liquidation import AssetLiquidationSkill
from reaper.skills.balance_transfer import (
    BalanceTransferOffer,
    BalanceTransferSkill,
    transfer_savings_cents,
)
from reaper.skills.base import SkillContext
from reaper.skills.charge_dispute import ChargeDisputeSkill
from reaper.skills.statement_audit import StatementAuditSkill, normalize_merchant
from reaper.skills.subscriptions import SubscriptionSkill


def context(
    config: ReaperConfig,
    workspace: Path,
    transactions: list[Transaction],
    inputs: dict | None = None,
) -> SkillContext:
    db = ReaperDB(config.agent.database)
    db.migrate()
    return SkillContext(
        config=config,
        db=db,
        transactions=transactions,
        workspace=workspace,
        inputs=inputs or {},
    )


def test_normalize_merchant_removes_statement_noise() -> None:
    assert normalize_merchant("VISA PURCHASE NETFLIX.COM 728291") == "netflix com"


def test_statement_audit_builds_baseline_and_anomaly(config: ReaperConfig, tmp_path: Path) -> None:
    transactions = [
        Transaction(posted_at=date(2026, 1, 1), description="Shop", amount_cents=1_000),
        Transaction(posted_at=date(2026, 2, 1), description="Shop", amount_cents=1_100),
        Transaction(posted_at=date(2026, 3, 1), description="Shop", amount_cents=30_000),
    ]
    result = StatementAuditSkill().run(context(config, tmp_path, transactions))
    assert len(result.opportunities) == 1
    assert result.opportunities[0].kind == "spend-anomaly"
    assert "3 transactions" in result.notes[0]


def test_subscription_skill_detects_monthly_charge(config: ReaperConfig, tmp_path: Path) -> None:
    transactions = [
        Transaction(posted_at=date(2026, month, 3), description="Netflix", amount_cents=1549)
        for month in range(1, 5)
    ]
    result = SubscriptionSkill().run(context(config, tmp_path, transactions))
    assert len(result.opportunities) == 1
    assert result.opportunities[0].estimated_monthly_savings_cents == 1549
    assert result.actions[0].verb == ActionVerb.CANCEL_SERVICE


def test_subscription_skill_ignores_irregular_amounts(config: ReaperConfig, tmp_path: Path) -> None:
    transactions = [
        Transaction(posted_at=date(2026, 1, 3), description="Store", amount_cents=1000),
        Transaction(posted_at=date(2026, 2, 3), description="Store", amount_cents=8000),
        Transaction(posted_at=date(2026, 3, 3), description="Store", amount_cents=2500),
    ]
    result = SubscriptionSkill().run(context(config, tmp_path, transactions))
    assert result.opportunities == []


def test_apr_skill_renders_three_messages(config: ReaperConfig) -> None:
    workspace = Path(__file__).resolve().parents[1]
    result = APRNegotiationSkill().run(context(config, workspace, []))
    assert len(result.actions) == 3
    assert result.actions[0].payload["stage"] == 1
    assert "26.99%" in result.actions[0].payload["body"]
    assert "Test Operator" in result.actions[0].payload["body"]
    assert all(action.verb == ActionVerb.SEND_EMAIL for action in result.actions)


def test_balance_transfer_math_matches_offer() -> None:
    offer = BalanceTransferOffer(
        provider="Credit Union",
        promo_apr_basis_points=0,
        promo_months=12,
        fee_basis_points=146,
        max_transfer_cents=610_000,
    )
    savings, breakdown = transfer_savings_cents(
        balance_cents=791_200,
        current_apr_basis_points=2699,
        offer=offer,
    )
    assert breakdown["transfer_cents"] == 610_000
    assert breakdown["transfer_fee_cents"] == 8906
    assert savings == 155_733


def test_balance_transfer_skill_emits_critical_action(config: ReaperConfig, tmp_path: Path) -> None:
    inputs = {
        "balance_transfer_offers": [
            {
                "provider": "Credit Union",
                "promo_apr_basis_points": 0,
                "promo_months": 12,
                "fee_basis_points": 300,
                "max_transfer_cents": 610_000,
            }
        ]
    }
    result = BalanceTransferSkill().run(context(config, tmp_path, [], inputs))
    assert len(result.opportunities) == 1
    assert result.actions[0].verb == ActionVerb.TRANSFER_BALANCE
    assert result.actions[0].risk.value == "critical"


def test_dispute_skill_finds_same_amount_duplicate(config: ReaperConfig, tmp_path: Path) -> None:
    transactions = [
        Transaction(posted_at=date(2026, 2, 17), description="Camera Shop", amount_cents=11_800),
        Transaction(posted_at=date(2026, 2, 17), description="Camera Shop", amount_cents=11_800),
    ]
    result = ChargeDisputeSkill().run(context(config, tmp_path, transactions))
    assert len(result.opportunities) == 1
    assert result.actions[0].payload["dispute_type"] == "duplicate_charge"


def test_asset_skill_requires_operator_selected_assets(
    config: ReaperConfig, tmp_path: Path
) -> None:
    inputs = {
        "assets": [
            {
                "name": "PlayStation 5",
                "category_id": "139971",
                "condition": "USED_EXCELLENT",
                "description": "Tested console",
                "estimated_price_cents": 38_900,
                "photo_paths": ["/tmp/front.jpg"],
            }
        ]
    }
    result = AssetLiquidationSkill().run(context(config, tmp_path, [], inputs))
    assert result.actions[0].verb == ActionVerb.PUBLISH_LISTING
    assert result.actions[0].payload["quantity"] == 1
