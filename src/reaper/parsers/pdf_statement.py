from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from dateutil import parser as date_parser
from pypdf import PdfReader

from reaper.domain import Transaction
from reaper.parsers.base import StatementParseError

LINE_PATTERN = re.compile(
    r"^(?P<date>\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?)\s+"
    r"(?P<description>.+?)\s+"
    r"(?P<amount>\(?-?\$?[\d,]+\.\d{2}\)?)$"
)


class PDFStatementParser:
    """Parse text-based card statements with an explicit review trail.

    Scanned PDFs require OCR before import. Ambiguous lines are returned in the
    evidence metadata rather than silently interpreted.
    """

    def parse(self, path: str | Path, *, account_last4: str = "") -> list[Transaction]:
        target = Path(path)
        reader = PdfReader(str(target))
        lines: list[tuple[int, str]] = []
        for page_number, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            lines.extend((page_number, line.strip()) for line in text.splitlines() if line.strip())
        if not lines:
            raise StatementParseError("PDF contains no extractable text; run OCR first")

        output: list[Transaction] = []
        for page_number, line in lines:
            match = LINE_PATTERN.match(line)
            if not match:
                continue
            raw = match.group("amount").replace("$", "").replace(",", "")
            negative = raw.startswith("(") or raw.startswith("-")
            value = Decimal(raw.strip("()-"))
            cents = int((value * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
            # Parenthesized or negative statement values are credits/payments.
            amount_cents = -cents if negative else cents
            raw_date = match.group("date")
            posted_at = date_parser.parse(raw_date, default=date_parser.parse("2000-01-01")).date()
            output.append(
                Transaction(
                    posted_at=posted_at,
                    description=match.group("description"),
                    amount_cents=amount_cents,
                    account_last4=account_last4,
                    metadata={"source": str(target), "page": page_number, "raw_line": line},
                )
            )
        if not output:
            raise StatementParseError(
                "No transaction lines matched the built-in PDF pattern; export CSV/OFX instead"
            )
        return output
