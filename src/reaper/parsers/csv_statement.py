from __future__ import annotations

import csv
import re
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path

from dateutil import parser as date_parser

from reaper.domain import Transaction
from reaper.parsers.base import StatementParseError

DATE_COLUMNS = ("date", "posted date", "posting date", "transaction date", "posted_at")
DESCRIPTION_COLUMNS = ("description", "merchant", "details", "memo", "name")
AMOUNT_COLUMNS = ("amount", "transaction amount", "value")
DEBIT_COLUMNS = ("debit", "withdrawal", "charge")
CREDIT_COLUMNS = ("credit", "deposit", "payment")
CATEGORY_COLUMNS = ("category", "type")
ID_COLUMNS = ("transaction id", "id", "reference")


def _normalized_header(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower().replace("_", " "))


def _pick(headers: dict[str, str], candidates: tuple[str, ...]) -> str | None:
    for candidate in candidates:
        if candidate in headers:
            return headers[candidate]
    return None


def _money_to_cents(raw: str | None) -> int:
    if raw is None or not raw.strip():
        return 0
    value = raw.strip().replace("$", "").replace(",", "")
    negative = value.startswith("(") and value.endswith(")")
    value = value.strip("()")
    try:
        decimal = Decimal(value)
    except InvalidOperation as exc:
        raise StatementParseError(f"Invalid amount: {raw!r}") from exc
    if negative:
        decimal = -decimal
    return int((decimal * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


class CSVStatementParser:
    """Parse common bank CSV exports into a stable transaction model.

    Expenses are represented as positive cents and credits/payments as negative cents.
    If the export has one signed amount column, negative values are treated as expenses,
    matching the convention used by most card issuers.
    """

    def parse(self, path: str | Path, *, account_last4: str = "") -> list[Transaction]:
        target = Path(path)
        with target.open(newline="", encoding="utf-8-sig") as handle:
            sample = handle.read(4096)
            handle.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
            except csv.Error:
                dialect = csv.excel
            reader = csv.DictReader(handle, dialect=dialect)
            if not reader.fieldnames:
                raise StatementParseError("CSV has no header row")
            headers = {_normalized_header(name): name for name in reader.fieldnames}
            date_key = _pick(headers, DATE_COLUMNS)
            description_key = _pick(headers, DESCRIPTION_COLUMNS)
            amount_key = _pick(headers, AMOUNT_COLUMNS)
            debit_key = _pick(headers, DEBIT_COLUMNS)
            credit_key = _pick(headers, CREDIT_COLUMNS)
            category_key = _pick(headers, CATEGORY_COLUMNS)
            id_key = _pick(headers, ID_COLUMNS)
            if not date_key or not description_key:
                raise StatementParseError(
                    f"Required date/description columns not found. Headers: {reader.fieldnames}"
                )
            if not amount_key and not debit_key and not credit_key:
                raise StatementParseError(
                    f"No amount, debit, or credit column found. Headers: {reader.fieldnames}"
                )

            output: list[Transaction] = []
            for line_number, row in enumerate(reader, start=2):
                if not any((value or "").strip() for value in row.values()):
                    continue
                try:
                    posted_at = date_parser.parse(row[date_key], fuzzy=False).date()
                except (ValueError, TypeError) as exc:
                    raise StatementParseError(
                        f"Line {line_number}: invalid date {row.get(date_key)!r}"
                    ) from exc
                description = (row.get(description_key) or "").strip()
                if not description:
                    raise StatementParseError(f"Line {line_number}: empty description")

                if amount_key:
                    signed = _money_to_cents(row.get(amount_key))
                    amount_cents = -signed
                    raw_sign = "signed-card-export"
                else:
                    debit = abs(_money_to_cents(row.get(debit_key))) if debit_key else 0
                    credit = abs(_money_to_cents(row.get(credit_key))) if credit_key else 0
                    amount_cents = debit - credit
                    raw_sign = "split-debit-credit"

                output.append(
                    Transaction(
                        posted_at=posted_at,
                        description=description,
                        amount_cents=amount_cents,
                        account_last4=account_last4,
                        category=(row.get(category_key) or "").strip() or None
                        if category_key
                        else None,
                        source_id=(row.get(id_key) or "").strip() or None if id_key else None,
                        metadata={
                            "source": str(target),
                            "line": line_number,
                            "amount_convention": raw_sign,
                            "imported_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                        },
                    )
                )
        return output
