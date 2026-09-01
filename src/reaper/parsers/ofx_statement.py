from __future__ import annotations

import re
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from reaper.domain import Transaction
from reaper.parsers.base import StatementParseError


def _tag(block: str, name: str) -> str | None:
    match = re.search(rf"<{name}>([^<\r\n]+)", block, flags=re.IGNORECASE)
    return match.group(1).strip() if match else None


class OFXStatementParser:
    """Read OFX/QFX transaction blocks without depending on issuer-specific SDKs."""

    def parse(self, path: str | Path, *, account_last4: str = "") -> list[Transaction]:
        target = Path(path)
        text = target.read_text(encoding="utf-8", errors="replace")
        blocks = re.findall(r"<STMTTRN>(.*?)(?:</STMTTRN>|(?=<STMTTRN>))", text, re.I | re.S)
        if not blocks:
            raise StatementParseError("No STMTTRN blocks found in OFX/QFX file")
        output: list[Transaction] = []
        for index, block in enumerate(blocks, start=1):
            raw_date = _tag(block, "DTPOSTED")
            raw_amount = _tag(block, "TRNAMT")
            description = _tag(block, "NAME") or _tag(block, "MEMO")
            if not raw_date or not raw_amount or not description:
                raise StatementParseError(
                    f"OFX transaction {index} is missing date, amount, or name"
                )
            posted_at = datetime.strptime(raw_date[:8], "%Y%m%d").date()
            signed = Decimal(raw_amount)
            cents = int((abs(signed) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
            # Card purchases are typically negative in OFX; payments are positive.
            amount_cents = cents if signed < 0 else -cents
            output.append(
                Transaction(
                    posted_at=posted_at,
                    description=description,
                    amount_cents=amount_cents,
                    account_last4=account_last4,
                    source_id=_tag(block, "FITID"),
                    metadata={
                        "source": str(target),
                        "transaction_type": _tag(block, "TRNTYPE"),
                    },
                )
            )
        return output
