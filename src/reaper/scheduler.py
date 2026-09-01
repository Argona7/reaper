from __future__ import annotations

import signal
import threading
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler  # type: ignore[import-untyped]
from apscheduler.triggers.cron import CronTrigger  # type: ignore[import-untyped]

from reaper.config import ReaperConfig
from reaper.connectors.telegram import TelegramConnector
from reaper.db import ReaperDB
from reaper.reporting import build_daily_report, format_telegram


def run_nightly_report(config: ReaperConfig, db: ReaperDB) -> str:
    report = build_daily_report(config, db)
    text = format_telegram(report, config.agent.name)
    if config.connectors.telegram.enabled:
        TelegramConnector().send(text)
        db.append_event("report.telegram.sent", {"report": report.model_dump(mode="json")})
    else:
        db.append_event("report.generated", {"report": report.model_dump(mode="json")})
    return text


def run_scheduler(config: ReaperConfig, db: ReaperDB) -> None:
    timezone = ZoneInfo(config.owner.timezone)
    scheduler = BackgroundScheduler(timezone=timezone)
    scheduler.add_job(
        run_nightly_report,
        trigger=CronTrigger(hour=config.owner.report_hour, minute=0, timezone=timezone),
        args=(config, db),
        id="reaper-nightly-report",
        name="Reaper nightly debt report",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
    )
    scheduler.start()
    stop = threading.Event()

    def request_stop(signum: int, _frame: object) -> None:
        del signum
        stop.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    stop.wait()
    scheduler.shutdown(wait=True)
