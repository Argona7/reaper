from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml
from pydantic import BaseModel, Field, field_validator

from reaper.domain import ActionVerb, DebtAccount


class OwnerConfig(BaseModel):
    name: str = "Operator"
    timezone: str = "UTC"
    report_hour: int = Field(default=21, ge=0, le=23)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Unknown timezone: {value}") from exc
        return value


class AgentConfig(BaseModel):
    name: str = "Reaper"
    model: str = "grok-4"
    currency: str = "USD"
    database: Path = Path(".reaper/reaper.sqlite3")
    evidence_dir: Path = Path(".reaper/evidence")


class ApprovalConfig(BaseModel):
    require_for: set[ActionVerb] = Field(
        default_factory=lambda: {
            ActionVerb.SEND_EMAIL,
            ActionVerb.CANCEL_SERVICE,
            ActionVerb.SUBMIT_DISPUTE,
            ActionVerb.TRANSFER_BALANCE,
            ActionVerb.MAKE_PAYMENT,
            ActionVerb.PUBLISH_LISTING,
            ActionVerb.EDIT_LISTING,
            ActionVerb.DELETE_LISTING,
            ActionVerb.SPEND,
        }
    )
    auto_allow: set[ActionVerb] = Field(
        default_factory=lambda: {
            ActionVerb.READ,
            ActionVerb.ANALYZE,
            ActionVerb.CALCULATE,
            ActionVerb.DRAFT,
            ActionVerb.REPORT,
        }
    )
    approval_ttl_minutes: int = Field(default=60, ge=1, le=10080)
    payment_cap_cents: int = Field(default=0, ge=0)


class GmailConfig(BaseModel):
    enabled: bool = False
    sender: str = "me"
    token_file: Path = Path(".reaper/google-token.json")


class TelegramConfig(BaseModel):
    enabled: bool = False


class EbayConfig(BaseModel):
    enabled: bool = False
    marketplace_id: str = "EBAY_US"


class ConnectorsConfig(BaseModel):
    gmail: GmailConfig = Field(default_factory=GmailConfig)
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    ebay: EbayConfig = Field(default_factory=EbayConfig)


class ReaperConfig(BaseModel):
    owner: OwnerConfig = Field(default_factory=OwnerConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    approval: ApprovalConfig = Field(default_factory=ApprovalConfig)
    debt: DebtAccount
    connectors: ConnectorsConfig = Field(default_factory=ConnectorsConfig)

    def resolve_paths(self, base_dir: Path) -> ReaperConfig:
        data = self.model_dump()
        for field in ("database", "evidence_dir"):
            path = Path(data["agent"][field]).expanduser()
            if not path.is_absolute():
                path = base_dir / path
            data["agent"][field] = path
        token_file = Path(data["connectors"]["gmail"]["token_file"]).expanduser()
        if not token_file.is_absolute():
            token_file = base_dir / token_file
        data["connectors"]["gmail"]["token_file"] = token_file
        return ReaperConfig.model_validate(data)


def load_config(path: str | Path | None = None) -> ReaperConfig:
    target = Path(path or os.environ.get("REAPER_CONFIG", "reaper.yaml")).expanduser().resolve()
    if not target.exists():
        raise FileNotFoundError(
            f"Configuration not found: {target}. Run `reaper init` or copy reaper.yaml.example."
        )
    raw: dict[str, Any] = yaml.safe_load(target.read_text()) or {}
    return ReaperConfig.model_validate(raw).resolve_paths(target.parent)
