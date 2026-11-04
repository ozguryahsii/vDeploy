"""Haftalık rapor: seçilen hafta (Pzt–Paz) için özet, önceki haftayla kıyas,
dikkat çeken kayıtlar ve otomatik yorum."""
from __future__ import annotations

import csv
import io
from collections import Counter
from datetime import date, timedelta

from sqlalchemy.orm import Session

from . import metrics, settings_store
from .models import OUTCOMES, ChangeRequest


RESOLUTION_BUCKETS = [("0–4 saat", 0, 4), ("4–12 saat", 4, 12), ("12–24 saat", 12, 24), ("1–3 gün", 24, 72),
                      ("3+ gün", 72, None)]


def _bucket(hours: float | None, buckets) -> str | None:
    if hours is None:
        return None
    for label, lo, hi in buckets:
        if (lo is None or hours >= lo) and (hi is None or hours < hi):
            return label
    return None


def _ms(d) -> int | None:
    return int(d.timestamp() * 1000) if d else None


def charts(changes: list[ChangeRequest], window, trend: dict, week: date) -> dict:
    """Rapor ekranındaki grafiklerin verisi (JSON olarak sayfaya gömülür)."""
    days = [{"inside": 0, "outside": 0} for _ in range(7)]
    hours = [{"inside": 0, "outside": 0} for _ in range(24)]
    for c in changes:
        t = metrics.deploy_time(c)
        if not t:
            continue
        side = "outside" if metrics.outside_window(c, window) else "inside"
        days[t.weekday()][side] += 1
        hours[t.hour][side] += 1

    res_counts = Counter(_bucket(metrics.resolution_hours(c), RESOLUTION_BUCKETS) for c in changes)
    s = metrics.summary(changes, window)
    no_date = sum(1 for c in changes if metrics.deploy_time(c) is None)
    risks = [
        ("Pencere dışı", s["outside_window"], "outside"),
        ("Geriye dönük kayıt", s["retroactive"], "retroactive"),
        ("Test yapılamıyor", sum(1 for c in changes if c.pre_test_possible is False or c.post_test_possible is False), "no_test"),
        ("Acil / kritik", s["emergency"], "emergency"),
        ("DB yapısal değişiklik", s["db_structural"], "db"),
        ("Açık talep", s["open"], "open"),
        ("Vendor'lu", s["vendor"], "vendor"),
    ]
    timeline = []
    for c in sorted(changes, key=lambda x: (x.deploy_planned or x.created)):
        timeline.append({
            "id": c.id, "key": c.jira_key or f"#{c.id}", "summary": c.summary, "app": c.application or "",
            "type": c.request_type, "created": _ms(c.created), "planned": _ms(c.deploy_planned),
            "resolved": _ms(c.resolved), "outside": metrics.outside_window(c, window), "emergency": c.is_emergency,
            "lead": metrics.lead_hours(c), "resolution": metrics.resolution_hours(c),
        })
    bd = metrics.breakdowns(changes, window)
    return {
        "week_start": week.isoformat(),
        "week_end": (week + timedelta(days=6)).isoformat(),
        "window": {"days": sorted(window.days), "start": window.start.hour, "end": window.end.hour},
        "days": days,
        "hours": hours,
        "share_window": [s["total"] - s["outside_window"] - no_date, s["outside_window"], no_date],
        "share_status": [s["closed"], s["open"]],
        "risks": [{"label": l, "value": v, "only": o} for l, v, o in risks],
        "lead_buckets": bd["lead_buckets"],
        "resolution_buckets": [{"label": l, "value": res_counts.get(l, 0)} for l, _, _ in RESOLUTION_BUCKETS],
        "request_type": bd["request_type"],
        "application": bd["application"],
        "microservice": bd["microservice"],
        "department": bd["department"],
        "assignee": bd["assignee"],
        "requester": bd["requester"],
        "timeline": timeline,
        "trend": trend,
    }


def build(db: Session, week: date) -> dict:
    week = metrics.week_start(week)
    values = settings_store.get_all(db)
    window = settings_store.window(values)
    cur_p = metrics.Period(week, week + timedelta(days=6))
    trend_p = metrics.Period(week - timedelta(weeks=7), cur_p.end)

    all_rows = db.query(ChangeRequest).all()
    cur = metrics.in_period(all_rows, cur_p)
    trend = metrics.breakdowns(metrics.in_period(all_rows, trend_p), window)["weekly"]

    s_cur = metrics.summary(cur, window)
    bd = metrics.breakdowns(cur, window)
    return {
        "week": week,
        "period": cur_p,
        "window": window,
        "summary": s_cur,
        "breakdowns": bd,
        "trend": trend,
        "charts": charts(cur, window, trend, week),
        "notable": metrics.notable(cur, window),
        "changes": sorted(cur, key=lambda c: c.ref_date),
        "commentary": commentary(s_cur, bd),
        "outcomes": OUTCOMES,
        "jira_url": values["jira.base_url"].rstrip("/"),
    }


def _n(v) -> str:
    """Türkçe ondalık: 40.0 -> 40, 42.5 -> 42,5"""
    return f"{v:g}".replace(".", ",") if isinstance(v, float) else str(v)


def _leader(rows: list[dict], skip=("Belirtilmemiş", "Atanmamış", "Diğer")) -> str | None:
    """En çok olan(lar)ı yazar; en yüksek sayı 2'den azsa (hepsi 1 ise) bilgi vermez."""
    rows = [r for r in rows if r["label"] not in skip]
    if not rows or rows[0]["value"] < 2:
        return None
    top = rows[0]["value"]
    names = [r["label"] for r in rows if r["value"] == top]
    if len(names) == 1:
        return f"{names[0]} ({top})"
    return f"{', '.join(names[:-1])} ve {names[-1]} ({top}'er)" if len(names) <= 4 else None


def commentary(cur: dict, bd: dict) -> list[str]:
    """Kural tabanlı kısa yorumlar. Önceki haftayla kıyas yapılmaz."""
    if cur["total"] == 0:
        return ["Bu hafta kayıtlı deployment talebi yok."]
    lines = [f"Bu hafta {cur['total']} deployment talebi var; {cur['closed']} kapalı, {cur['open']} açık."]
    for title, rows in (("En sık talep tipi", bd["request_type"]), ("En çok deploy çıkan uygulama", bd["application"]),
                        ("En çok değişen mikroservis", bd["microservice"]),
                        ("En çok talep açan departman", bd["department"])):
        leader = _leader(rows)
        if leader:
            lines.append(f"{title}: {leader}.")
    if cur["outside_window"]:
        lines.append(f"{cur['outside_window']} talep (%{_n(cur['outside_window_rate'])}) bakım penceresi dışında planlanmış.")
    else:
        lines.append("Tüm talepler bakım penceresi içinde planlanmış.")
    if cur["retroactive"]:
        lines.append(f"{cur['retroactive']} talepte deploy tarihi, talebin açılışından önce; kayıt iş yapıldıktan sonra açılmış görünüyor.")
    if cur["short_notice_rate"] is not None and cur["short_notice_rate"] >= 50:
        lines.append(f"Taleplerin %{_n(cur['short_notice_rate'])}'i deploy'dan 24 saatten kısa süre önce açılmış.")
    if cur["median_resolution_hours"] is not None:
        lines.append(f"Medyan çözüm süresi {_n(cur['median_resolution_hours'])} saat.")
    if cur["emergency"]:
        lines.append(f"{cur['emergency']} acil/kritik deployment var.")
    if cur["no_pre_test"] or cur["no_post_test"]:
        lines.append(f"Test yapılamayan talepler: deploy öncesi {cur['no_pre_test']}, deploy sonrası {cur['no_post_test']}.")
    if cur["db_structural"]:
        lines.append(f"{cur['db_structural']} talepte veritabanında yapısal değişiklik var.")
    if cur["vendor"]:
        lines.append(f"{cur['vendor']} talep vendor üzerinden yürütülmüş.")
    if cur["change_failure_rate"] is not None:
        lines.append(f"Sonucu girilen {cur['outcome_judged']} talepte başarısızlık/geri alma oranı %{_n(cur['change_failure_rate'])}.")
    return lines


def to_csv(changes: list[ChangeRequest], window) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow([
        "Jira", "Özet", "Talep tipi", "Uygulama", "Mikroservisler", "Departman", "Talep eden", "Uygulayan",
        "Oluşturma", "Planlanan deploy", "Çözüm", "Durum", "Acil", "Pencere dışı", "Sonuç", "Not",
    ])
    fmt = lambda d: d.strftime("%d.%m.%Y %H:%M") if d else ""  # noqa: E731
    for c in changes:
        w.writerow([
            c.jira_key or "", c.summary, c.request_type, c.application or "", c.microservices or "",
            c.department or "", c.requester or "", c.assignee or "", fmt(c.created), fmt(c.deploy_planned),
            fmt(c.resolved), c.status, "Evet" if c.is_emergency else "Hayır",
            "Evet" if metrics.outside_window(c, window) else "Hayır", OUTCOMES.get(c.outcome, c.outcome), c.notes or "",
        ])
    return ("﻿" + buf.getvalue()).encode("utf-8")  # Excel Türkçe karakterleri doğru açsın
