from __future__ import annotations

from pathlib import Path
from typing import Protocol

from reaper.domain import Transaction


class StatementParser(Protocol):
    def parse(self, path: str | Path, *, account_last4: str = "") -> list[Transaction]: ...


class StatementParseError(ValueError):
    """Raised when a statement cannot be mapped without guessing."""
