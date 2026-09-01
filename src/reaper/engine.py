from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from reaper.approvals import ApprovalPolicy
from reaper.config import ReaperConfig
from reaper.connectors.ebay import EbayConnector
from reaper.connectors.gmail import GmailConnector
from reaper.db import ReaperDB
from reaper.domain import ActionStatus, ActionVerb, ProposedAction, SkillResult
from reaper.skills import ALL_SKILLS
from reaper.skills.base import SkillContext


class ReaperEngine:
    def __init__(self, config: ReaperConfig, workspace: str | Path) -> None:
        self.config = config
        self.workspace = Path(workspace).resolve()
        self.db = ReaperDB(config.agent.database)
        self.db.migrate()
        self.policy = ApprovalPolicy(config.approval)

    def run_skills(self, inputs: dict[str, Any] | None = None) -> list[SkillResult]:
        context = SkillContext(
            config=self.config,
            db=self.db,
            transactions=self.db.list_transactions(),
            workspace=self.workspace,
            inputs=inputs or {},
        )
        results: list[SkillResult] = []
        for skill_type in ALL_SKILLS:
            result = skill_type().run(context)
            for opportunity in result.opportunities:
                self.db.add_opportunity(opportunity)
            persisted_actions: list[ProposedAction] = []
            for action in result.actions:
                decision = self.policy.evaluate(action)
                prepared = action.model_copy(
                    update={
                        "status": self.policy.initial_status(action),
                        "expires_at": decision.expires_at,
                    }
                )
                persisted_actions.append(self.db.add_action(prepared))
            results.append(result.model_copy(update={"actions": persisted_actions}))
            self.db.append_event(
                "skill.completed",
                {
                    "skill": result.skill,
                    "opportunities": len(result.opportunities),
                    "actions": len(result.actions),
                    "notes": result.notes,
                },
            )
        return results

    def approve(self, action_id: str, *, actor: str, reason: str | None = None) -> ProposedAction:
        from reaper.domain import ApprovalRecord

        return self.db.decide_action(
            ApprovalRecord(
                action_id=action_id,
                decision=ActionStatus.APPROVED,
                actor=actor,
                reason=reason,
            )
        )

    def reject(self, action_id: str, *, actor: str, reason: str | None = None) -> ProposedAction:
        from reaper.domain import ApprovalRecord

        return self.db.decide_action(
            ApprovalRecord(
                action_id=action_id,
                decision=ActionStatus.REJECTED,
                actor=actor,
                reason=reason,
            )
        )

    def execute(self, action_id: str) -> dict[str, Any]:
        action = self.db.get_action(action_id)
        if action.status != ActionStatus.APPROVED:
            raise PermissionError(f"Action {action_id} is {action.status}; approval is required")
        self.db.update_action_status(action.id, ActionStatus.EXECUTING)
        try:
            result = self._execute_action(action)
        except Exception as exc:
            self.db.update_action_status(action.id, ActionStatus.FAILED, error=str(exc))
            self.db.append_event(
                "action.failed",
                {"action_id": action.id, "verb": action.verb.value, "error": str(exc)},
            )
            raise
        self.db.update_action_status(action.id, ActionStatus.SUCCEEDED, result=result)
        self.db.append_event(
            "action.succeeded",
            {"action_id": action.id, "verb": action.verb.value, "result": result},
        )
        return result

    def _execute_action(self, action: ProposedAction) -> dict[str, Any]:
        if action.verb == ActionVerb.SEND_EMAIL:
            if not self.config.connectors.gmail.enabled:
                raise RuntimeError("Gmail connector is disabled")
            gmail = GmailConnector(
                token_file=self.config.connectors.gmail.token_file,
                sender=self.config.connectors.gmail.sender,
            )
            return gmail.send(
                to=str(action.payload.get("to", "")),
                subject=str(action.payload["subject"]),
                body=str(action.payload["body"]),
            )
        if action.verb == ActionVerb.PUBLISH_LISTING:
            if not self.config.connectors.ebay.enabled:
                raise RuntimeError("eBay connector is disabled")
            ebay = EbayConnector(marketplace_id=self.config.connectors.ebay.marketplace_id)
            return ebay.publish_listing(action.payload)
        if action.verb in {
            ActionVerb.CANCEL_SERVICE,
            ActionVerb.SUBMIT_DISPUTE,
            ActionVerb.TRANSFER_BALANCE,
            ActionVerb.MAKE_PAYMENT,
            ActionVerb.SPEND,
        }:
            raise RuntimeError(
                f"{action.verb.value} has no universal API. Export the approved action package "
                "and complete it in the issuer or merchant channel configured for this account."
            )
        raise RuntimeError(f"No executor registered for {action.verb.value}")

    def export_action(self, action_id: str, destination: str | Path) -> Path:
        action = self.db.get_action(action_id)
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(action.model_dump_json(indent=2), encoding="utf-8")
        return target


def load_inputs(*paths: str | Path) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for path in paths:
        target = Path(path)
        if not target.exists():
            raise FileNotFoundError(target)
        if target.suffix.lower() == ".json":
            data = json.loads(target.read_text())
        else:
            data = yaml.safe_load(target.read_text()) or {}
        for key, value in data.items():
            if isinstance(value, list):
                merged.setdefault(key, []).extend(value)
            elif isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key].update(value)
            else:
                merged[key] = value
    return merged
