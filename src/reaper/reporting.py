from __future__ import annotations

import math
from datetime import date, timedelta

from reaper.config import ReaperConfig
from reaper.db import ReaperDB
from reaper.domain import DailyReport


def project_zero_date(balance_cents: int, monthly_principal_cents: int) -> date | None:
    if balance_cents <= 0:
        return date.today()
    if monthly_principal_cents <= 0:
        return None
    months = math.ceil(balance_cents / monthly_principal_cents)
    return date.today() + timedelta(days=round(months * 30.4375))


def build_daily_report(
    config: ReaperConfig,
    db: ReaperDB,
    *,
    freed_today_cents: int = 0,
) -> DailyReport:
    counts = db.summary_counts()
    opportunities = db.list_opportunities()
    recurring = sum(item.estimated_monthly_savings_cents for item in opportunities)
    one_time = sum(item.estimated_one_time_savings_cents for item in opportunities)
    debt = config.debt
    projected_monthly = debt.minimum_payment_cents + recurring
    report = DailyReport(
        debt_balance_cents=debt.current_balance_cents,
        principal_reduced_cents=debt.principal_reduced_cents,
        freed_today_cents=freed_today_cents,
        recurring_savings_cents=recurring,
        pending_approvals=counts["pending_approvals"],
        actions_succeeded=counts["actions_succeeded"],
        projected_zero_date=project_zero_date(debt.current_balance_cents, projected_monthly),
        lines=[
            f"Transactions read: {counts['transactions']}",
            f"Opportunities found: {counts['opportunities']}",
            f"Potential one-time recovery: ${one_time / 100:,.2f}",
        ],
    )
    db.put_daily_snapshot(
        snapshot_date=date.today().isoformat(),
        debt_balance_cents=report.debt_balance_cents,
        freed_today_cents=report.freed_today_cents,
        recurring_savings_cents=report.recurring_savings_cents,
        payload=report.model_dump(mode="json"),
    )
    return report


def format_telegram(report: DailyReport, agent_name: str = "Reaper") -> str:
    zero = report.projected_zero_date.isoformat() if report.projected_zero_date else "not projected"
    return "\n".join(
        [
            f"{agent_name} daily report",
            f"debt: ${report.debt_balance_cents / 100:,.2f}",
            f"principal killed: ${report.principal_reduced_cents / 100:,.2f}",
            f"freed today: ${report.freed_today_cents / 100:,.2f}",
            f"recurring savings found: ${report.recurring_savings_cents / 100:,.2f}/mo",
            f"pending approvals: {report.pending_approvals}",
            f"projected zero: {zero}",
            "nothing was sent, spent, transferred, cancelled, disputed, or listed without approval",
        ]
    )
