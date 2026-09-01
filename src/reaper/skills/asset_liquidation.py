from __future__ import annotations

from pydantic import BaseModel, Field

from reaper.domain import ActionVerb, Opportunity, ProposedAction, RiskLevel, SkillResult
from reaper.skills.base import SkillContext


class AssetCandidate(BaseModel):
    name: str
    category_id: str
    condition: str
    description: str
    estimated_price_cents: int = Field(gt=0)
    photo_paths: list[str] = Field(min_length=1)
    sku: str | None = None


class AssetLiquidationSkill:
    name = "asset-liquidation"
    description = "Price unused assets and prepare eBay inventory/offers for explicit approval."

    def run(self, context: SkillContext) -> SkillResult:
        assets = [AssetCandidate.model_validate(item) for item in context.inputs.get("assets", [])]
        opportunities: list[Opportunity] = []
        actions: list[ProposedAction] = []
        for asset in assets:
            evidence = [
                f"Condition: {asset.condition}",
                f"Estimated resale: ${asset.estimated_price_cents / 100:,.2f}",
                f"Photos: {len(asset.photo_paths)}",
            ]
            opportunities.append(
                Opportunity(
                    skill=self.name,
                    kind="asset-sale",
                    title=f"Sell unused {asset.name}",
                    estimated_one_time_savings_cents=asset.estimated_price_cents,
                    confidence=0.65,
                    evidence=evidence,
                    metadata=asset.model_dump(),
                )
            )
            actions.append(
                ProposedAction(
                    skill=self.name,
                    verb=ActionVerb.PUBLISH_LISTING,
                    title=f"Publish eBay listing for {asset.name}",
                    risk=RiskLevel.CRITICAL,
                    payload={
                        "sku": asset.sku or asset.name.lower().replace(" ", "-")[:50],
                        "title": asset.name[:80],
                        "description": asset.description,
                        "category_id": asset.category_id,
                        "condition": asset.condition,
                        "price_cents": asset.estimated_price_cents,
                        "photo_paths": asset.photo_paths,
                        "quantity": 1,
                    },
                    evidence=evidence,
                )
            )
        return SkillResult(
            skill=self.name,
            opportunities=opportunities,
            actions=actions,
            notes=[f"Prepared {len(assets)} asset listings; none were published."],
        )
