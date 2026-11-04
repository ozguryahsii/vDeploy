"""Jira CSV export'u ve Jira REST yanıtlarını ortak bir biçime çevirip
veritabanına yazar (Jira anahtarına göre ekle/güncelle).

Alanlar Jira'daki *görünen adlarıyla* eşlenir; böylece aynı tablo hem CSV
başlıkları ("Özel alan (Deployment Tarihi)") hem REST API (`expand=names`)
için çalışır ve customfield_xxxxx numaralarını bilmek gerekmez.
"""
from __future__ import annotations

import csv
import io
import re
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from . import config
from .models import ChangeRequest

FIELD_ALIASES: dict[str, list[str]] = {
    "key": ["Talep anahtarı", "Issue key", "Anahtar", "key"],
    "summary": ["Özet", "Summary"],
    "request_type": ["Customer Request Type", "Müşteri Talep Tipi", "Request Type"],
    "status": ["Durum", "Status"],
    "requester": ["Raporlayan", "Reporter"],
    "assignee": ["Atanan", "Assignee"],
    "department": ["Reporter Department", "Departman"],
    "application": ["Web uygulaması"],
    "microservices": ["Microservisler"],
    "database": ["Veri Tabanı"],
    "db_type": ["Veri Tabanı Tipi"],
    "db_structural": ["Veri Tabanında Yapısal Bir Değişiklik Yapılıyor mu?"],
    "vendor": ["Vendor"],
    "vendor_ticket": ["Vendor Ticket Id"],
    "tag": ["Deploy Edilmesi İstenen Tag No"],
    "emergency_reason": ["Deployment Kritik Acil Nedeni"],
    "priority": ["Deployment Önceliği"],
    "pre_test": ["Deployment Öncesi Test Yapılabilir?"],
    "post_test": ["Deployment sonrası test yapılabilir?"],
    "created": ["Oluşturma", "Created"],
    "resolved": ["Çözme", "Resolved"],
    "deploy_planned": ["Deployment Tarihi"],
}

_WRAPPER = re.compile(r"^(?:Özel alan|Custom field)\s*\((.*)\)\s*$")
_ASSET_SUFFIX = re.compile(r"\s*\((?:[A-Z]+-\d+|JIRAUSER\d+)\)\s*$")
_EMPTY = {"", "-", "'-", "x", ".", "yok", "none", "null"}
_DATE_FORMATS = [
    "%d.%m.%Y %H:%M",
    "%d.%m.%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%d/%b/%y %I:%M %p",
    "%d/%b/%Y %I:%M %p",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%d.%m.%Y",
]


def _norm_name(name: str) -> str:
    m = _WRAPPER.match(name.strip())
    return (m.group(1) if m else name).strip().casefold()


_ALIAS_LOOKUP = {alias.casefold(): canon for canon, aliases in FIELD_ALIASES.items() for alias in aliases}


def clean(value: str | None) -> str | None:
    if value is None:
        return None
    v = _ASSET_SUFFIX.sub("", str(value).strip()).strip()
    return None if v.casefold() in _EMPTY else v


def parse_dt(value: str | None) -> datetime | None:
    v = (value or "").strip()
    if not v:
        return None
    try:  # REST API: 2026-10-08T19:00:00.000+0300
        iso = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", v)
        d = datetime.fromisoformat(iso)
        if d.tzinfo:
            d = d.astimezone(ZoneInfo(config.TIMEZONE)).replace(tzinfo=None)
        return d.replace(microsecond=0)
    except ValueError:
        pass
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(v, fmt)
        except ValueError:
            continue
    return None


def parse_bool(value: str | None) -> bool | None:
    v = (clean(value) or "").casefold()
    if v in {"evet", "yes", "true", "1"}:
        return True
    if v in {"hayır", "hayir", "no", "false", "0"}:
        return False
    return None


def canonicalize(fields: dict[str, list[str]]) -> dict[str, list[str]]:
    """{'Jira alan adı': [değerler]} -> {'kanonik_ad': [değerler]}"""
    out: dict[str, list[str]] = defaultdict(list)
    for name, values in fields.items():
        canon = _ALIAS_LOOKUP.get(_norm_name(name))
        if canon:
            out[canon].extend(v for v in values if v is not None)
    return out


def _first(row: dict[str, list[str]], key: str) -> str | None:
    for v in row.get(key, []):
        c = clean(v)
        if c:
            return c
    return None


def to_record(row: dict[str, list[str]], closed_statuses: set[str]) -> dict | None:
    key = _first(row, "key")
    created = parse_dt(_first(row, "created"))
    if not key or not created:
        return None
    micro: list[str] = []
    for v in row.get("microservices", []):
        for part in str(v).split(","):
            c = clean(part)
            if c and c not in micro:
                micro.append(c)
    status = _first(row, "status") or ""
    emergency_reason = _first(row, "emergency_reason")
    priority = (_first(row, "priority") or "").casefold()
    return {
        "jira_key": key,
        "summary": (_first(row, "summary") or "")[:500],
        "request_type": _first(row, "request_type") or "Diğer",
        "status": status,
        "is_closed": status.casefold() in closed_statuses,
        "requester": _first(row, "requester"),
        "assignee": _first(row, "assignee"),
        "department": _first(row, "department"),
        "application": _first(row, "application"),
        "microservices": ", ".join(micro) or None,
        "database": _first(row, "database"),
        "db_type": _first(row, "db_type"),
        "db_structural_change": parse_bool(_first(row, "db_structural")),
        "vendor": _first(row, "vendor"),
        "vendor_ticket": _first(row, "vendor_ticket"),
        "tag": _first(row, "tag"),
        "is_emergency": bool(emergency_reason) or any(w in priority for w in ("acil", "kritik", "emergency", "critical")),
        "emergency_reason": emergency_reason,
        "pre_test_possible": parse_bool(_first(row, "pre_test")),
        "post_test_possible": parse_bool(_first(row, "post_test")),
        "created": created,
        "resolved": parse_dt(_first(row, "resolved")),
        "deploy_planned": parse_dt(_first(row, "deploy_planned")),
    }


def rows_from_csv(content: bytes) -> list[dict[str, list[str]]]:
    text = content.decode("utf-8-sig", errors="replace")
    sample = text[:4096]
    delimiter = ";" if sample.count(";") > sample.count(",") else ","
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    header = next(reader, [])
    rows = []
    for raw in reader:
        if not any(c.strip() for c in raw):
            continue
        fields: dict[str, list[str]] = defaultdict(list)
        for name, value in zip(header, raw):
            fields[name].append(value)
        rows.append(canonicalize(fields))
    return rows


def upsert(db: Session, records: list[dict], source: str) -> tuple[int, int]:
    inserted = updated = 0
    for rec in records:
        existing = db.query(ChangeRequest).filter_by(jira_key=rec["jira_key"]).one_or_none()
        if existing is None:
            db.add(ChangeRequest(source=source, **rec))
            inserted += 1
        else:
            # Uygulamada girilen sonuç/not alanlarına dokunulmaz.
            for k, v in rec.items():
                setattr(existing, k, v)
            updated += 1
    db.commit()
    return inserted, updated


def import_csv(db: Session, content: bytes, closed_statuses: set[str]) -> tuple[int, int, int]:
    rows = rows_from_csv(content)
    records = [r for r in (to_record(row, closed_statuses) for row in rows) if r]
    ins, upd = upsert(db, records, "csv")
    return ins, upd, len(rows) - len(records)
