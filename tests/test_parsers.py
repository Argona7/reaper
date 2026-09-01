from __future__ import annotations

from pathlib import Path

import pytest

from reaper.parsers import CSVStatementParser, OFXStatementParser, PDFStatementParser
from reaper.parsers.base import StatementParseError


def test_csv_parser_normalizes_signed_card_amounts(tmp_path: Path) -> None:
    statement = tmp_path / "statement.csv"
    statement.write_text(
        "Date,Description,Amount,Transaction ID\n"
        "2026-01-02,NETFLIX,-15.49,a\n"
        "2026-01-04,PAYMENT,500.00,b\n"
    )
    items = CSVStatementParser().parse(statement, account_last4="4242")
    assert [item.amount_cents for item in items] == [1549, -50_000]
    assert items[0].account_last4 == "4242"
    assert items[0].fingerprint != items[1].fingerprint


def test_csv_parser_supports_debit_credit_columns(tmp_path: Path) -> None:
    statement = tmp_path / "statement.csv"
    statement.write_text(
        "Posting Date,Merchant,Debit,Credit\n01/02/2026,Coffee,4.25,\n01/03/2026,Refund,,2.00\n"
    )
    items = CSVStatementParser().parse(statement)
    assert [item.amount_cents for item in items] == [425, -200]


def test_csv_parser_rejects_unknown_schema(tmp_path: Path) -> None:
    statement = tmp_path / "statement.csv"
    statement.write_text("when,where,total\n2026-01-02,Coffee,4.25\n")
    with pytest.raises(StatementParseError, match="Required date/description"):
        CSVStatementParser().parse(statement)


def test_ofx_parser_reads_purchase_and_payment(tmp_path: Path) -> None:
    statement = tmp_path / "statement.ofx"
    statement.write_text(
        """
<OFX><BANKMSGSRSV1><STMTTRNRS><STMTRS><BANKTRANLIST>
<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20260102120000<TRNAMT>-12.34<FITID>1<NAME>COFFEE</STMTTRN>
<STMTTRN><TRNTYPE>CREDIT<DTPOSTED>20260103120000<TRNAMT>500.00<FITID>2<NAME>PAYMENT</STMTTRN>
</BANKTRANLIST></STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>
"""
    )
    items = OFXStatementParser().parse(statement)
    assert [item.amount_cents for item in items] == [1234, -50_000]
    assert [item.source_id for item in items] == ["1", "2"]


def test_pdf_parser_reads_text_lines(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    statement = tmp_path / "statement.pdf"
    statement.write_bytes(b"pdf")

    class Page:
        def extract_text(self) -> str:
            return "01/02/2026 COFFEE SHOP 12.34\n01/03/2026 REFUND (2.00)"

    class Reader:
        def __init__(self) -> None:
            self.pages = [Page()]

    monkeypatch.setattr("reaper.parsers.pdf_statement.PdfReader", lambda _: Reader())
    items = PDFStatementParser().parse(statement, account_last4="4242")
    assert [item.amount_cents for item in items] == [1234, -200]
    assert items[0].metadata["page"] == 1


def test_pdf_parser_rejects_scanned_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    statement = tmp_path / "scan.pdf"
    statement.write_bytes(b"pdf")

    class Page:
        def extract_text(self) -> str:
            return ""

    class Reader:
        def __init__(self) -> None:
            self.pages = [Page()]

    monkeypatch.setattr("reaper.parsers.pdf_statement.PdfReader", lambda _: Reader())
    with pytest.raises(StatementParseError, match="no extractable text"):
        PDFStatementParser().parse(statement)
