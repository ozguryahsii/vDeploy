"""Ayarlar ekranından yönetilen değerler (key/value tablosu)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import time

from sqlalchemy.orm import Session

from .models import Setting

DEFAULTS: dict[str, str] = {
    # Bakım penceresi: haftanın günleri 0=Pzt ... 6=Paz
    "window.days": "3",
    "window.start": "18:00",
    "window.end": "23:59",
    # Jira (Data Center / Server)
    "jira.base_url": "",
    "jira.pat": "",
    "jira.jql": 'project = SAY AND issuetype = "Deployment Talebi" AND updated >= -8d ORDER BY created ASC',
    "jira.verify_ssl": "1",
    "jira.closed_statuses": "Kapalı,Closed,Done,Çözüldü,Resolved,Tamamlandı",
    "jira.auto_sync": "0",
    # SMTP
    "smtp.host": "",
    "smtp.port": "25",
    "smtp.security": "none",  # none | starttls | ssl
    "smtp.user": "",
    "smtp.password": "",
    "smtp.from": "",
    "smtp.to": "",
    "smtp.auto_send": "0",
    # Haftalık otomatik iş (Jira senkronu + rapor e-postası)
    "schedule.day": "fri",
    "schedule.time": "09:00",
    # Active Directory (LDAP) - varsayılan kapalı
    "ad.enabled": "0",
    "ad.server": "",
    "ad.port": "636",
    "ad.use_ssl": "1",
    "ad.domain": "",
    "ad.base_dn": "",
    "ad.allowed_group": "",
}

SECRET_KEYS = {"jira.pat", "smtp.password"}
DAY_NAMES = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]


def get_all(db: Session) -> dict[str, str]:
    values = dict(DEFAULTS)
    for row in db.query(Setting).all():
        values[row.key] = row.value
    return values


def get(db: Session, key: str) -> str:
    row = db.get(Setting, key)
    return row.value if row else DEFAULTS.get(key, "")


def set_many(db: Session, values: dict[str, str]) -> None:
    for key, value in values.items():
        if key not in DEFAULTS:
            continue
        # Gizli alan boş gönderildiyse mevcut değeri koru (form maskeli gösteriyor).
        if key in SECRET_KEYS and value == "":
            continue
        row = db.get(Setting, key)
        if row is None:
            db.add(Setting(key=key, value=value))
        else:
            row.value = value
    db.commit()


def truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "on", "yes", "evet"}


@dataclass(frozen=True)
class Window:
    days: frozenset[int]
    start: time
    end: time

    def contains(self, moment) -> bool:
        if moment.weekday() not in self.days:
            return False
        t = moment.time()
        if self.start <= self.end:
            return self.start <= t <= self.end
        return t >= self.start or t <= self.end  # gece yarısını aşan pencere

    def describe(self) -> str:
        days = ", ".join(DAY_NAMES[d] for d in sorted(self.days)) or "—"
        return f"{days} {self.start:%H:%M}–{self.end:%H:%M}"


def _parse_time(value: str, fallback: str) -> time:
    try:
        h, m = (value or fallback).split(":")[:2]
        return time(int(h), int(m))
    except ValueError:
        h, m = fallback.split(":")
        return time(int(h), int(m))


def window(values: dict[str, str]) -> Window:
    days = frozenset(int(d) for d in values.get("window.days", "").split(",") if d.strip().isdigit())
    return Window(
        days=days,
        start=_parse_time(values.get("window.start", ""), "18:00"),
        end=_parse_time(values.get("window.end", ""), "23:59"),
    )
