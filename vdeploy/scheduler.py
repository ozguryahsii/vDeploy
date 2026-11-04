"""Haftalık otomatik iş: (açıksa) Jira senkronu, ardından (açıksa) rapor e-postası."""
from __future__ import annotations

import logging
from datetime import date, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from . import config, jira_client, mailer, settings_store
from .db import SessionLocal

log = logging.getLogger("vdeploy.scheduler")
JOB_ID = "weekly"
_scheduler: BackgroundScheduler | None = None


def weekly_job() -> None:
    from .web import render_report_email  # döngüsel importu önlemek için

    with SessionLocal() as db:
        values = settings_store.get_all(db)
        if settings_store.truthy(values["jira.auto_sync"]):
            result = jira_client.sync(db)
            log.info("Jira senkronu: ok=%s %s", result.ok, result.message)
        if settings_store.truthy(values["smtp.auto_send"]) and mailer.is_configured(values):
            last_week = date.today() - timedelta(days=7)
            render_report_email(db, last_week, values)


def reschedule(values: dict[str, str]) -> str | None:
    if _scheduler is None:
        return None
    hh, mm = (values["schedule.time"] or "09:00").split(":")[:2]
    trigger = CronTrigger(day_of_week=values["schedule.day"] or "fri", hour=int(hh), minute=int(mm),
                          timezone=config.TIMEZONE)
    _scheduler.add_job(weekly_job, trigger, id=JOB_ID, replace_existing=True)
    job = _scheduler.get_job(JOB_ID)
    return job.next_run_time.strftime("%d.%m.%Y %H:%M") if job and job.next_run_time else None


def start() -> None:
    global _scheduler
    if _scheduler is not None or not config.SCHEDULER_ENABLED:
        return
    _scheduler = BackgroundScheduler(timezone=config.TIMEZONE)
    _scheduler.start()
    with SessionLocal() as db:
        reschedule(settings_store.get_all(db))


def stop() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def next_run() -> str | None:
    if _scheduler is None:
        return None
    job = _scheduler.get_job(JOB_ID)
    return job.next_run_time.strftime("%d.%m.%Y %H:%M") if job and job.next_run_time else None
