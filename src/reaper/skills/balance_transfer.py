from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from pydantic import BaseModel, Field

from reaper.domain import ActionVerb, Opportunity, ProposedAction, RiskLevel, SkillResult
from reaper.skills.base import SkillContext


class BalanceTransferOffer(BaseModel):
    provider: str
    promo_apr_basis_points: int = Field(ge=0)
    promo_months: int = Field(gt=0)
    fee_basis_points: int = Field(ge=0)
    max_transfer_cents: int = Field(gt=0)
    offer_url: str | None = None


def transfer_savings_cents(
    *,
    balance_cents: int,
    current_apr_basis_points: int,
    offer: BalanceTransferOffer,
) -> tuple[int, dict[str, int]]:
    transferable = min(balance_cents, offer.max_transfer_cents)
    months = offer.promo_months
    current_interest = (
        Decimal(transferable)
        * Decimal(current_apr_basis_points)
        / Decimal(10_000)
        * Decimal(months)
        / Decimal(12)
    )
    promo_interest = (
        Decimal(transferable)
        * Decimal(offer.promo_apr_basis_points)
        / Decimal(10_000)
        * Decimal(months)
        / Decimal(12)
    )
    fee = Decimal(transferable) * Decimal(offer.fee_basis_points) / Decimal(10_000)
    savings = max(Decimal(0), current_interest - promo_interest - fee)

    def rounded(value: Decimal) -> int:
        return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    return rounded(savings), {
        "transfer_cents": transferable,
        "estimated_current_interest_cents": rounded(current_interest),
        "estimated_promo_interest_cents": rounded(promo_interest),
        "transfer_fee_cents": rounded(fee),
    }


class BalanceTransferSkill:
    name = "balance-transfer"
    description = "Compare promotional transfer offers and surface positive net savings."

    def run(self, context: SkillContext) -> SkillResult:
        raw_offers = context.inputs.get("balance_transfer_offers", [])
        offers = [BalanceTransferOffer.model_validate(item) for item in raw_offers]
        opportunities: list[Opportunity] = []
        actions: list[ProposedAction] = []
        for offer in offers:
            savings, breakdown = transfer_savings_cents(
                balance_cents=context.config.debt.current_balance_cents,
                current_apr_basis_points=context.config.debt.apr_basis_points,
                offer=offer,
            )
            if savings <= 0:
                continue
            interest_avoided_cents = (
                breakdown["estimated_current_interest_cents"]
                - breakdown["estimated_promo_interest_cents"]
            )
            evidence = [
                f"Transfer amount: ${breakdown['transfer_cents'] / 100:,.2f}",
                f"Transfer fee: ${breakdown['transfer_fee_cents'] / 100:,.2f}",
                f"Estimated interest avoided: ${interest_avoided_cents / 100:,.2f}",
            ]
            opportunities.append(
                Opportunity(
                    skill=self.name,
                    kind="balance-transfer",
                    title=f"{offer.promo_months}-month offer from {offer.provider}",
                    estimated_one_time_savings_cents=savings,
                    confidence=0.72,
                    evidence=evidence,
                    metadata={"offer": offer.model_dump(), "breakdown": breakdown},
                )
            )
            actions.append(
                ProposedAction(
                    skill=self.name,
                    verb=ActionVerb.TRANSFER_BALANCE,
                    title=f"Transfer balance to {offer.provider}",
                    risk=RiskLevel.CRITICAL,
                    payload={
                        "offer": offer.model_dump(),
                        "breakdown": breakdown,
                        "estimated_savings_cents": savings,
                        "operator_must_verify": [
                            "eligibility",
                            "credit limit",
                            "post-promo APR",
                            "transfer deadline",
                            "issuer terms",
                        ],
                    },
                    evidence=evidence,
                )
            )
        return SkillResult(
            skill=self.name,
            opportunities=opportunities,
            actions=actions,
            notes=[f"Evaluated {len(offers)} balance-transfer offers."],
        )
