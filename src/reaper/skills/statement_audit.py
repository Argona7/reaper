from __future__ import annotations

import re
from collections import Counter, defaultdict
from statistics import median

from reaper.domain import Opportunity, SkillResult
from reaper.skills.base import SkillContext

MERCHANT_NOISE = re.compile(
    r"\b(?:purchase|debit|credit|card|visa|mastercard|pos|recurring|payment|online)\b|\d{3,}",
    re.IGNORECASE,
)


def normalize_merchant(description: str) -> str:
    cleaned = MERCHANT_NOISE.sub(" ", description.lower())
    cleaned = re.sub(r"[^a-z0-9&' ]+", " ", cleaned)
    return " ".join(cleaned.split()).strip() or description.lower().strip()


class StatementAuditSkill:
    name = "statement-audit"
    description = "Build a 14-month transaction map, cash-flow baseline, and anomaly list."

    def run(self, context: SkillContext) -> SkillResult:
        transactions = context.transactions
        if not transactions:
            return SkillResult(skill=self.name, notes=["No transactions imported."])

        expenses = [item for item in transactions if item.amount_cents > 0]
        credits = [item for item in transactions if item.amount_cents < 0]
        by_month: dict[str, int] = defaultdict(int)
        for item in expenses:
            by_month[item.posted_at.strftime("%Y-%m")] += item.amount_cents

        merchant_totals: Counter[str] = Counter()
        merchant_counts: Counter[str] = Counter()
        for item in expenses:
            merchant = normalize_merchant(item.description)
            merchant_totals[merchant] += item.amount_cents
            merchant_counts[merchant] += 1

        opportunities: list[Opportunity] = []
        amounts_by_merchant: dict[str, list[int]] = defaultdict(list)
        for item in expenses:
            amounts_by_merchant[normalize_merchant(item.description)].append(item.amount_cents)

        for merchant, amounts in amounts_by_merchant.items():
            if len(amounts) < 2:
                continue
            center = median(amounts)
            for item in expenses:
                if normalize_merchant(item.description) != merchant:
                    continue
                if item.amount_cents >= center * 2.5 and item.amount_cents >= 10_000:
                    opportunities.append(
                        Opportunity(
                            skill=self.name,
                            kind="spend-anomaly",
                            title=f"Review unusual {merchant} charge",
                            estimated_one_time_savings_cents=item.amount_cents,
                            confidence=0.62,
                            evidence=[
                                f"{item.posted_at.isoformat()} {item.description}: "
                                f"${item.amount_cents / 100:,.2f}",
                                f"Median prior amount: ${center / 100:,.2f}",
                            ],
                            metadata={"transaction_fingerprint": item.fingerprint},
                        )
                    )

        notes = [
            f"Imported {len(transactions)} transactions across {len(by_month)} months.",
            f"Expenses: ${sum(item.amount_cents for item in expenses) / 100:,.2f}.",
            f"Credits/payments: ${abs(sum(item.amount_cents for item in credits)) / 100:,.2f}.",
        ]
        if by_month:
            notes.append(f"Median monthly card spend: ${median(by_month.values()) / 100:,.2f}.")
        return SkillResult(skill=self.name, opportunities=opportunities, notes=notes)
