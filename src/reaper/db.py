from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from reaper.domain import (
    ActionStatus,
    ApprovalRecord,
    Opportunity,
    ProposedAction,
    Transaction,
    utc_now,
)

SCHEMA_VERSION = 1


class ReaperDB:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 5000")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def migrate(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_meta (
                    version INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS transactions (
                    fingerprint TEXT PRIMARY KEY,
                    posted_at TEXT NOT NULL,
                    description TEXT NOT NULL,
                    amount_cents INTEGER NOT NULL,
                    account_last4 TEXT NOT NULL,
                    category TEXT,
                    source_id TEXT,
                    metadata_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS opportunities (
                    id TEXT PRIMARY KEY,
                    skill TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    title TEXT NOT NULL,
                    monthly_savings_cents INTEGER NOT NULL,
                    one_time_savings_cents INTEGER NOT NULL,
                    confidence REAL NOT NULL,
                    evidence_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS actions (
                    id TEXT PRIMARY KEY,
                    skill TEXT NOT NULL,
                    verb TEXT NOT NULL,
                    title TEXT NOT NULL,
                    risk TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    expires_at TEXT,
                    result_json TEXT,
                    error TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_actions_status ON actions(status, created_at);
                CREATE TABLE IF NOT EXISTS approvals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action_id TEXT NOT NULL REFERENCES actions(id),
                    decision TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    reason TEXT,
                    decided_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS daily_snapshots (
                    snapshot_date TEXT PRIMARY KEY,
                    debt_balance_cents INTEGER NOT NULL,
                    freed_today_cents INTEGER NOT NULL,
                    recurring_savings_cents INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            current = conn.execute("SELECT version FROM schema_meta LIMIT 1").fetchone()
            if current is None:
                conn.execute("INSERT INTO schema_meta(version) VALUES (?)", (SCHEMA_VERSION,))
            elif int(current["version"]) != SCHEMA_VERSION:
                raise RuntimeError(
                    f"Unsupported schema version {current['version']}; expected {SCHEMA_VERSION}"
                )

    def add_transactions(self, transactions: Sequence[Transaction]) -> int:
        inserted = 0
        with self.connect() as conn:
            for item in transactions:
                cursor = conn.execute(
                    """
                    INSERT OR IGNORE INTO transactions(
                        fingerprint, posted_at, description, amount_cents, account_last4,
                        category, source_id, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item.fingerprint,
                        item.posted_at.isoformat(),
                        item.description,
                        item.amount_cents,
                        item.account_last4,
                        item.category,
                        item.source_id,
                        json.dumps(item.metadata, sort_keys=True, default=str),
                    ),
                )
                inserted += cursor.rowcount
        return inserted

    def list_transactions(self) -> list[Transaction]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM transactions ORDER BY posted_at ASC, rowid ASC"
            ).fetchall()
        return [
            Transaction(
                posted_at=row["posted_at"],
                description=row["description"],
                amount_cents=row["amount_cents"],
                account_last4=row["account_last4"],
                category=row["category"],
                source_id=row["source_id"],
                metadata=json.loads(row["metadata_json"]),
            )
            for row in rows
        ]

    def add_opportunity(self, opportunity: Opportunity) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO opportunities(
                    id, skill, kind, title, monthly_savings_cents, one_time_savings_cents,
                    confidence, evidence_json, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    opportunity.id,
                    opportunity.skill,
                    opportunity.kind,
                    opportunity.title,
                    opportunity.estimated_monthly_savings_cents,
                    opportunity.estimated_one_time_savings_cents,
                    opportunity.confidence,
                    json.dumps(opportunity.evidence, sort_keys=True),
                    json.dumps(opportunity.metadata, sort_keys=True, default=str),
                    utc_now().isoformat(),
                ),
            )

    def list_opportunities(self) -> list[Opportunity]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM opportunities ORDER BY created_at DESC").fetchall()
        return [
            Opportunity(
                id=row["id"],
                skill=row["skill"],
                kind=row["kind"],
                title=row["title"],
                estimated_monthly_savings_cents=row["monthly_savings_cents"],
                estimated_one_time_savings_cents=row["one_time_savings_cents"],
                confidence=row["confidence"],
                evidence=json.loads(row["evidence_json"]),
                metadata=json.loads(row["metadata_json"]),
            )
            for row in rows
        ]

    def add_action(self, action: ProposedAction) -> ProposedAction:
        key = action.stable_idempotency_key()
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT * FROM actions WHERE idempotency_key = ?", (key,)
            ).fetchone()
            if existing:
                return self._row_to_action(existing)
            conn.execute(
                """
                INSERT INTO actions(
                    id, skill, verb, title, risk, payload_json, evidence_json, status,
                    idempotency_key, created_at, updated_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    action.id,
                    action.skill,
                    action.verb.value,
                    action.title,
                    action.risk.value,
                    json.dumps(action.payload, sort_keys=True, default=str),
                    json.dumps(action.evidence, sort_keys=True),
                    action.status.value,
                    key,
                    action.created_at.isoformat(),
                    action.updated_at.isoformat(),
                    action.expires_at.isoformat() if action.expires_at else None,
                ),
            )
        return action.model_copy(update={"idempotency_key": key})

    def get_action(self, action_id: str) -> ProposedAction:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM actions WHERE id = ?", (action_id,)).fetchone()
        if row is None:
            raise KeyError(f"Unknown action: {action_id}")
        return self._row_to_action(row)

    def list_actions(self, status: ActionStatus | None = None) -> list[ProposedAction]:
        query = "SELECT * FROM actions"
        params: tuple[Any, ...] = ()
        if status is not None:
            query += " WHERE status = ?"
            params = (status.value,)
        query += " ORDER BY created_at DESC"
        with self.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_action(row) for row in rows]

    def decide_action(self, record: ApprovalRecord) -> ProposedAction:
        if record.decision not in {ActionStatus.APPROVED, ActionStatus.REJECTED}:
            raise ValueError("Approval decision must be approved or rejected")
        now = record.decided_at.isoformat()
        with self.connect() as conn:
            row = conn.execute(
                "SELECT status FROM actions WHERE id = ?", (record.action_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"Unknown action: {record.action_id}")
            if row["status"] != ActionStatus.PROPOSED.value:
                raise ValueError(f"Action is already {row['status']}")
            conn.execute(
                "UPDATE actions SET status = ?, updated_at = ? WHERE id = ?",
                (record.decision.value, now, record.action_id),
            )
            conn.execute(
                """
                INSERT INTO approvals(action_id, decision, actor, reason, decided_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    record.action_id,
                    record.decision.value,
                    record.actor,
                    record.reason,
                    now,
                ),
            )
        return self.get_action(record.action_id)

    def update_action_status(
        self,
        action_id: str,
        status: ActionStatus,
        *,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> ProposedAction:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE actions
                SET status = ?, updated_at = ?, result_json = ?, error = ?
                WHERE id = ?
                """,
                (
                    status.value,
                    utc_now().isoformat(),
                    json.dumps(result, sort_keys=True, default=str) if result is not None else None,
                    error,
                    action_id,
                ),
            )
        return self.get_action(action_id)

    def append_event(self, event_type: str, payload: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO events(event_type, payload_json, created_at) VALUES (?, ?, ?)",
                (
                    event_type,
                    json.dumps(payload, sort_keys=True, default=str),
                    utc_now().isoformat(),
                ),
            )

    def put_daily_snapshot(
        self,
        *,
        snapshot_date: str,
        debt_balance_cents: int,
        freed_today_cents: int,
        recurring_savings_cents: int,
        payload: dict[str, Any],
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO daily_snapshots(
                    snapshot_date, debt_balance_cents, freed_today_cents,
                    recurring_savings_cents, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot_date,
                    debt_balance_cents,
                    freed_today_cents,
                    recurring_savings_cents,
                    json.dumps(payload, sort_keys=True, default=str),
                    utc_now().isoformat(),
                ),
            )

    def latest_snapshot(self) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM daily_snapshots ORDER BY snapshot_date DESC LIMIT 1"
            ).fetchone()
        if row is None:
            return None
        return {
            "snapshot_date": row["snapshot_date"],
            "debt_balance_cents": row["debt_balance_cents"],
            "freed_today_cents": row["freed_today_cents"],
            "recurring_savings_cents": row["recurring_savings_cents"],
            "payload": json.loads(row["payload_json"]),
            "created_at": row["created_at"],
        }

    def summary_counts(self) -> dict[str, int]:
        with self.connect() as conn:
            transactions = conn.execute("SELECT COUNT(*) AS n FROM transactions").fetchone()["n"]
            opportunities = conn.execute("SELECT COUNT(*) AS n FROM opportunities").fetchone()["n"]
            pending = conn.execute(
                "SELECT COUNT(*) AS n FROM actions WHERE status = ?",
                (ActionStatus.PROPOSED.value,),
            ).fetchone()["n"]
            succeeded = conn.execute(
                "SELECT COUNT(*) AS n FROM actions WHERE status = ?",
                (ActionStatus.SUCCEEDED.value,),
            ).fetchone()["n"]
        return {
            "transactions": int(transactions),
            "opportunities": int(opportunities),
            "pending_approvals": int(pending),
            "actions_succeeded": int(succeeded),
        }

    @staticmethod
    def _row_to_action(row: sqlite3.Row) -> ProposedAction:
        return ProposedAction(
            id=row["id"],
            skill=row["skill"],
            verb=row["verb"],
            title=row["title"],
            risk=row["risk"],
            payload=json.loads(row["payload_json"]),
            evidence=json.loads(row["evidence_json"]),
            status=row["status"],
            idempotency_key=row["idempotency_key"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            expires_at=datetime.fromisoformat(row["expires_at"]) if row["expires_at"] else None,
        )
