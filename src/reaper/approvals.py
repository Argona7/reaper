from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from reaper.config import ApprovalConfig
from reaper.domain import ActionStatus, ProposedAction, utc_now


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    requires_approval: bool
    reason: str
    expires_at: datetime | None = None


class ApprovalPolicy:
    """Central policy boundary for every side effect Reaper can request."""

    def __init__(self, config: ApprovalConfig) -> None:
        self.config = config

    def evaluate(self, action: ProposedAction) -> PolicyDecision:
        if action.verb in self.config.require_for:
            return PolicyDecision(
                requires_approval=True,
                reason=f"{action.verb.value} is configured as an approval-required side effect",
                expires_at=utc_now() + timedelta(minutes=self.config.approval_ttl_minutes),
            )
        if action.verb in self.config.auto_allow:
            return PolicyDecision(
                requires_approval=False,
                reason=f"{action.verb.value} is a read-only or draft operation",
            )
        return PolicyDecision(
            requires_approval=True,
            reason=f"{action.verb.value} has no explicit auto-allow rule",
            expires_at=utc_now() + timedelta(minutes=self.config.approval_ttl_minutes),
        )

    def initial_status(self, action: ProposedAction) -> ActionStatus:
        decision = self.evaluate(action)
        return ActionStatus.PROPOSED if decision.requires_approval else ActionStatus.APPROVED
