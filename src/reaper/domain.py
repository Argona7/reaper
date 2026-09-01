from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


def utc_now() -> datetime:
    return datetime.now(UTC)


class ActionVerb(StrEnum):
    READ = "read"
    ANALYZE = "analyze"
    CALCULATE = "calculate"
    DRAFT = "draft"
    REPORT = "report"
    SEND_EMAIL = "send_email"
    CANCEL_SERVICE = "cancel_service"
    SUBMIT_DISPUTE = "submit_dispute"
    TRANSFER_BALANCE = "transfer_balance"
    MAKE_PAYMENT = "make_payment"
    PUBLISH_LISTING = "publish_listing"
    EDIT_LISTING = "edit_listing"
    DELETE_LISTING = "delete_listing"
    SPEND = "spend"


class ActionStatus(StrEnum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTING = "executing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    EXPIRED = "expired"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Transaction(BaseModel):
    model_config = ConfigDict(frozen=True)

    posted_at: date
    description: str = Field(min_length=1, max_length=500)
    amount_cents: int
    account_last4: str = Field(default="", max_length=4)
    category: str | None = None
    source_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("description")
    @classmethod
    def clean_description(cls, value: str) -> str:
        return " ".join(value.strip().split())

    @property
    def fingerprint(self) -> str:
        parts = (
            self.posted_at.isoformat(),
            self.description.lower(),
            str(self.amount_cents),
            self.account_last4,
            self.source_id or "",
        )
        raw = "|".join(parts)
        return hashlib.sha256(raw.encode()).hexdigest()


class DebtAccount(BaseModel):
    issuer: str
    account_last4: str = Field(pattern=r"^\d{4}$")
    starting_balance_cents: int = Field(ge=0)
    current_balance_cents: int = Field(ge=0)
    apr_basis_points: int = Field(ge=0, le=10000)
    minimum_payment_cents: int = Field(ge=0)
    statement_day: int = Field(ge=1, le=31)

    @property
    def apr_percent(self) -> Decimal:
        return Decimal(self.apr_basis_points) / Decimal(100)

    @property
    def principal_reduced_cents(self) -> int:
        return max(0, self.starting_balance_cents - self.current_balance_cents)


class Opportunity(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    skill: str
    kind: str
    title: str
    estimated_monthly_savings_cents: int = 0
    estimated_one_time_savings_cents: int = 0
    confidence: float = Field(ge=0, le=1)
    evidence: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProposedAction(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    skill: str
    verb: ActionVerb
    title: str
    risk: RiskLevel
    payload: dict[str, Any] = Field(default_factory=dict)
    evidence: list[str] = Field(default_factory=list)
    status: ActionStatus = ActionStatus.PROPOSED
    idempotency_key: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime | None = None

    def stable_idempotency_key(self) -> str:
        if self.idempotency_key:
            return self.idempotency_key
        raw = json.dumps(
            {"skill": self.skill, "verb": self.verb, "payload": self.payload},
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(raw.encode()).hexdigest()


class ApprovalRecord(BaseModel):
    action_id: str
    decision: ActionStatus
    actor: str
    reason: str | None = None
    decided_at: datetime = Field(default_factory=utc_now)


class SkillResult(BaseModel):
    skill: str
    opportunities: list[Opportunity] = Field(default_factory=list)
    actions: list[ProposedAction] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class DailyReport(BaseModel):
    generated_at: datetime = Field(default_factory=utc_now)
    debt_balance_cents: int
    principal_reduced_cents: int
    freed_today_cents: int
    recurring_savings_cents: int
    pending_approvals: int
    actions_succeeded: int
    projected_zero_date: date | None = None
    lines: list[str] = Field(default_factory=list)
