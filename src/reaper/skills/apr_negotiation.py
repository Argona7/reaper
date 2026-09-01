from __future__ import annotations

from pathlib import Path

from reaper.domain import ActionVerb, ProposedAction, RiskLevel, SkillResult
from reaper.skills.base import SkillContext


def render_template(path: Path, values: dict[str, str]) -> str:
    text = path.read_text(encoding="utf-8")
    for key, value in values.items():
        text = text.replace("{{ " + key + " }}", value)
    return text


class APRNegotiationSkill:
    name = "apr-negotiation"
    description = "Run the issuer retention escalation that asks for a durable APR reduction."

    def run(self, context: SkillContext) -> SkillResult:
        debt = context.config.debt
        playbooks = context.workspace / "playbooks" / "apr-retention"
        values = {
            "owner_name": context.config.owner.name,
            "issuer": debt.issuer,
            "account_last4": debt.account_last4,
            "current_apr": f"{debt.apr_percent:.2f}%",
            "current_balance": f"${debt.current_balance_cents / 100:,.2f}",
        }
        actions: list[ProposedAction] = []
        for stage, filename, subject in (
            (
                1,
                "01-initial-retention.md",
                "APR review request for account ending {{ account_last4 }}",
            ),
            (2, "02-supervisor-escalation.md", "Escalation: written APR review request"),
            (3, "03-written-confirmation.md", "Request for written confirmation of APR terms"),
        ):
            body = render_template(playbooks / filename, values)
            rendered_subject = subject.replace("{{ account_last4 }}", debt.account_last4)
            actions.append(
                ProposedAction(
                    skill=self.name,
                    verb=ActionVerb.SEND_EMAIL,
                    title=f"APR retention email {stage}/3 to {debt.issuer}",
                    risk=RiskLevel.HIGH,
                    payload={
                        "stage": stage,
                        "to": "",
                        "subject": rendered_subject,
                        "body": body,
                        "requires_previous_stage": stage > 1,
                    },
                    evidence=[
                        f"Current APR: {debt.apr_percent:.2f}%",
                        f"Current balance: ${debt.current_balance_cents / 100:,.2f}",
                    ],
                )
            )
        return SkillResult(
            skill=self.name,
            actions=actions,
            notes=[
                f"Prepared a three-step retention escalation for {debt.issuer}; "
                "no message was sent."
            ],
        )
