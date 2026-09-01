from __future__ import annotations

from pathlib import Path

import pytest

from reaper.config import ReaperConfig, load_config
from reaper.domain import ActionVerb


def test_load_config_resolves_runtime_paths(tmp_path: Path) -> None:
    config_file = tmp_path / "reaper.yaml"
    config_file.write_text(
        """
owner:
  timezone: UTC
agent:
  database: runtime/reaper.sqlite3
  evidence_dir: runtime/evidence
debt:
  issuer: Example Bank
  account_last4: '4242'
  starting_balance_cents: 840000
  current_balance_cents: 791200
  apr_basis_points: 2699
  minimum_payment_cents: 22000
  statement_day: 7
"""
    )
    loaded = load_config(config_file)
    assert loaded.agent.database == tmp_path / "runtime/reaper.sqlite3"
    assert loaded.agent.evidence_dir == tmp_path / "runtime/evidence"
    assert ActionVerb.SEND_EMAIL in loaded.approval.require_for


def test_invalid_timezone_is_rejected(config: ReaperConfig) -> None:
    data = config.model_dump()
    data["owner"]["timezone"] = "Mars/Olympus"
    with pytest.raises(ValueError):
        ReaperConfig.model_validate(data)
