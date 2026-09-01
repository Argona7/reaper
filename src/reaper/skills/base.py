from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from reaper.config import ReaperConfig
from reaper.db import ReaperDB
from reaper.domain import SkillResult, Transaction


@dataclass(slots=True)
class SkillContext:
    config: ReaperConfig
    db: ReaperDB
    transactions: list[Transaction]
    workspace: Path
    inputs: dict[str, Any] = field(default_factory=dict)


class ReaperSkill(Protocol):
    name: str
    description: str

    def run(self, context: SkillContext) -> SkillResult: ...
