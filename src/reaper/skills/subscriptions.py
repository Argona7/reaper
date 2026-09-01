from __future__ import annotations

from collections import defaultdict
from itertools import pairwise
from statistics import median

from reaper.domain import (
    ActionVerb,
    Opportunity,
    ProposedAction,
    RiskLevel,
    SkillResult,
    Transaction,
)
from reaper.skills.base import SkillContext
from reaper.skills.statement_audit import normalize_merchant


def _looks_monthly(days: list[int]) -> bool:
    if len(days) < 2:
        return False
    return sum(25 <= value <= 35 for value in days) / len(days) >= 0.66


def _looks_annual(days: list[int]) -> bool:
    return any(350 <= value <= 380 for value in days)


class SubscriptionSkill:
    name = "subscriptions"
    description = "Find recurring charges and prepare cancellable subscription actions."

    def run(self, context: SkillContext) -> SkillResult:
        grouped: dict[str, list[Transaction]] = defaultdict(list)
        for item in context.transactions:
            if item.amount_cents > 0:
                grouped[normalize_merchant(item.description)].append(item)

        opportunities: list[Opportunity] = []
        actions: list[ProposedAction] = []
        for merchant, items in grouped.items():
            items.sort(key=lambda item: item.posted_at)
            if len(items) < 2:
                continue
            gaps = [(right.posted_at - left.posted_at).days for left, right in pairwise(items)]
            amounts = [item.amount_cents for item in items]
            center = int(median(amounts))
            stable = max(abs(value - center) for value in amounts) <= max(100, center * 0.15)
            cadence = (
                "monthly" if _looks_monthly(gaps) else "annual" if _looks_annual(gaps) else None
            )
            if not cadence or not stable:
                continue
            monthly = center if cadence == "monthly" else center // 12
            evidence = [
                f"{item.posted_at.isoformat()} {item.description}: ${item.amount_cents / 100:,.2f}"
                for item in items[-4:]
            ]
            opportunity = Opportunity(
                skill=self.name,
                kind="recurring-charge",
                title=f"{merchant.title()} recurring charge",
                estimated_monthly_savings_cents=monthly,
                confidence=min(0.98, 0.72 + 0.05 * len(items)),
                evidence=evidence,
                metadata={"merchant": merchant, "cadence": cadence, "amount_cents": center},
            )
            opportunities.append(opportunity)
            actions.append(
                ProposedAction(
                    skill=self.name,
                    verb=ActionVerb.CANCEL_SERVICE,
                    title=f"Cancel {merchant.title()} after operator review",
                    risk=RiskLevel.HIGH,
                    payload={
                        "merchant": merchant,
                        "cadence": cadence,
                        "amount_cents": center,
                        "reason": "Recurring charge identified from statement history",
                        "draft_only": True,
                    },
                    evidence=evidence,
                )
            )

        total = sum(item.estimated_monthly_savings_cents for item in opportunities)
        return SkillResult(
            skill=self.name,
            opportunities=opportunities,
            actions=actions,
            notes=[
                f"Found {len(opportunities)} recurring charges worth ${total / 100:,.2f}/month."
            ],
        )
