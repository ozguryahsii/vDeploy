from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import time
from functools import lru_cache
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    """Minimal .env okuyucu: var olan ortam değişkenlerini ezmez."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "evet"}


def _time(value: str | None, default: str) -> time:
    h, m = (value or default).split(":")
    return time(int(h), int(m))


@dataclass(frozen=True)
class Settings:
    database_url: str = "sqlite:///./vdeploy.db"
    app_base_url: str = "http://localhost:8000"
    timezone: str = "Europe/Istanbul"

    maint_window_start: time = time(22, 0)
    maint_window_end: time = time(6, 0)
    maint_weekend_allowed: bool = True

    jira_deployment: str = "server"
    jira_base_url: str = ""
    jira_pat: str = ""
    jira_user: str = ""
    jira_api_token: str = ""
    jira_jql: str = "project = CHG AND updated >= -8d ORDER BY created ASC"
    jira_mapping_file: str = "config/jira_mapping.yaml"
    jira_verify_ssl: bool | str = True

    smtp_host: str = ""
    smtp_port: int = 25
    smtp_starttls: bool = False
    smtp_user: str = ""
    smtp_password: str = ""
    report_from: str = "vdeploy@localhost"
    report_to: list[str] = field(default_factory=list)

    scheduler_enabled: bool = False
    weekly_job_day: str = "mon"
    weekly_job_time: time = time(8, 0)

    @classmethod
    def from_env(cls) -> "Settings":
        _load_dotenv(Path(os.environ.get("VDEPLOY_ENV_FILE", ".env")))
        e = os.environ.get
        verify_raw = e("JIRA_VERIFY_SSL", "true")
        verify: bool | str = (
            _bool(verify_raw, True) if verify_raw.lower() in {"true", "false", "1", "0", "yes", "no"} else verify_raw
        )
        return cls(
            database_url=e("DATABASE_URL", cls.database_url),
            app_base_url=e("APP_BASE_URL", cls.app_base_url).rstrip("/"),
            timezone=e("TIMEZONE", cls.timezone),
            maint_window_start=_time(e("MAINT_WINDOW_START"), "22:00"),
            maint_window_end=_time(e("MAINT_WINDOW_END"), "06:00"),
            maint_weekend_allowed=_bool(e("MAINT_WEEKEND_ALLOWED"), True),
            jira_deployment=e("JIRA_DEPLOYMENT", "server").lower(),
            jira_base_url=e("JIRA_BASE_URL", "").rstrip("/"),
            jira_pat=e("JIRA_PAT", ""),
            jira_user=e("JIRA_USER", ""),
            jira_api_token=e("JIRA_API_TOKEN", ""),
            jira_jql=e("JIRA_JQL", cls.jira_jql),
            jira_mapping_file=e("JIRA_MAPPING_FILE", cls.jira_mapping_file),
            jira_verify_ssl=verify,
            smtp_host=e("SMTP_HOST", ""),
            smtp_port=int(e("SMTP_PORT", "25")),
            smtp_starttls=_bool(e("SMTP_STARTTLS"), False),
            smtp_user=e("SMTP_USER", ""),
            smtp_password=e("SMTP_PASSWORD", ""),
            report_from=e("REPORT_FROM", cls.report_from),
            report_to=[x.strip() for x in e("REPORT_TO", "").split(",") if x.strip()],
            scheduler_enabled=_bool(e("SCHEDULER_ENABLED"), False),
            weekly_job_day=e("WEEKLY_JOB_DAY", "mon"),
            weekly_job_time=_time(e("WEEKLY_JOB_TIME"), "08:00"),
        )


@lru_cache
def get_settings() -> Settings:
    return Settings.from_env()
