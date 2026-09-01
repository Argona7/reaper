from __future__ import annotations

from pathlib import Path

import pytest

from reaper.config import ReaperConfig


@pytest.fixture
def config(tmp_path: Path) -> ReaperConfig:
    return ReaperConfig.model_validate(
        {
            "owner": {"name": "Test Operator", "timezone": "UTC", "report_hour": 21},
            "agent": {
                "name": "Reaper",
                "model": "grok-4",
                "currency": "USD",
                "database": tmp_path / "reaper.sqlite3",
                "evidence_dir": tmp_path / "evidence",
            },
            "debt": {
                "issuer": "Example Bank",
                "account_last4": "4242",
                "starting_balance_cents": 840_000,
                "current_balance_cents": 791_200,
                "apr_basis_points": 2699,
                "minimum_payment_cents": 22_000,
                "statement_day": 7,
            },
        }
    )
