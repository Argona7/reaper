from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from itertools import pairwise

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


class ChargeDisputeSkill:
    name = "charge-dispute"
    description = "Find likely duplicate charges and assemble evidence-first dispute packets."

    def run(self, context: SkillContext) -> SkillResult:
        grouped: dict[tuple[str, int], list[Transaction]] = defaultdict(list)
        for item in context.transactions:
            if item.amount_cents > 0:
                grouped[(normalize_merchant(item.description), item.amount_cents)].append(item)

        opportunities: list[Opportunity] = []
        actions: list[ProposedAction] = []
        for (merchant, amount_cents), items in grouped.items():
            items.sort(key=lambda item: item.posted_at)
            for left, right in pairwise(items):
                if right.posted_at - left.posted_at > timedelta(days=3):
                    continue
                evidence = [
                    f"{left.posted_at.isoformat()} {left.description}: ${amount_cents / 100:,.2f}",
                    f"{right.posted_at.isoformat()} {right.description}: "
                    f"${amount_cents / 100:,.2f}",
                ]
                opportunity = Opportunity(
                    skill=self.name,
                    kind="possible-duplicate",
                    title=f"Possible duplicate {merchant.title()} charge",
                    estimated_one_time_savings_cents=amount_cents,
                    confidence=0.78 if left.posted_at == right.posted_at else 0.68,
                    evidence=evidence,
                    metadata={
                        "transaction_fingerprints": [left.fingerprint, right.fingerprint],
                        "merchant": merchant,
                    },
                )
                opportunities.append(opportunity)
                actions.append(
                    ProposedAction(
                        skill=self.name,
                        verb=ActionVerb.SUBMIT_DISPUTE,
                        title=f"Submit duplicate-charge dispute for {merchant.title()}",
                        risk=RiskLevel.CRITICAL,
                        payload={
                            "dispute_type": "duplicate_charge",
                            "merchant": merchant,
                            "amount_cents": amount_cents,
                            "transaction_fingerprints": [left.fingerprint, right.fingerprint],
                            "statement": (
                                "I am requesting review of two charges with the same merchant and "
                                "amount posted within three days. Please confirm whether both were "
                                "separately authorized before opening a formal dispute."
                            ),
                        },
                        evidence=evidence,
                    )
                )
        return SkillResult(
            skill=self.name,
            opportunities=opportunities,
            actions=actions,
            notes=[f"Found {len(opportunities)} possible duplicate charges for operator review."],
        )
