from __future__ import annotations

import json
import os
from typing import Any

from openai import OpenAI
from pydantic import BaseModel, Field


class DraftMessage(BaseModel):
    subject: str
    body: str
    factual_basis: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)


class GrokDraftingClient:
    """Small, typed xAI client used only for grounded drafts.

    Deterministic money calculations and policy decisions stay outside the model.
    """

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        key = api_key or os.environ.get("XAI_API_KEY")
        if not key:
            raise RuntimeError("XAI_API_KEY is not configured")
        self.model = model or os.environ.get("GROK_MODEL", "grok-4")
        self.client = OpenAI(api_key=key, base_url="https://api.x.ai/v1")

    def draft(
        self,
        *,
        objective: str,
        facts: list[str],
        constraints: list[str],
        template: str | None = None,
    ) -> DraftMessage:
        payload: dict[str, Any] = {
            "objective": objective,
            "facts": facts,
            "constraints": constraints,
            "template": template,
        }
        response = self.client.chat.completions.create(
            model=self.model,
            temperature=0.1,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You draft factual personal-finance operations messages. Use only supplied "
                        "facts. Never invent an account event, bank response, eligibility, "
                        "approval, or legal conclusion. Return JSON with subject, body, "
                        "factual_basis, and missing_fields."
                    ),
                },
                {"role": "user", "content": json.dumps(payload, sort_keys=True)},
            ],
        )
        content = response.choices[0].message.content
        if not content:
            raise RuntimeError("Grok returned an empty draft")
        return DraftMessage.model_validate_json(content)
