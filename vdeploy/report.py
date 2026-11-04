"""Haftalık rapor: seçilen hafta (Pzt–Paz) için özet, önceki haftayla kıyas,
dikkat çeken kayıtlar ve otomatik yorum."""
from __future__ import annotations

import csv
import io
from datetime import date, timedelta

from sqlalchemy.orm import Session

from . import metrics, settings_store
from .models import OUTCOMES, ChangeRequest


def build(db: Session, week: date) -> dict:
    week = metrics.week_start(week)
    values = settings_store.get_all(db)
    window = settings_store.window(values)
    cur_p = metrics.Period(week, week + timedelta(days=6))
    prev_p = metrics.Period(week - timedelta(days=7), week - timedelta(days=1))
    # Kıyas için son 8 haftalık trend
    trend_p = metrics.Period(week - timedelta(weeks=7), cur_p.end)

    all_rows = db.query(ChangeRequest).all()
    cur = metrics.in_period(all_rows, cur_p)
    prev = metrics.in_period(all_rows, prev_p)
    trend = metrics.in_period(all_rows, trend_p)

    s_cur = metrics.summary(cur, window)
    s_prev = metrics.summary(prev, window)
    return {
        "week": week,
        "period": cur_p,
        "window": window,
        "summary": s_cur,
        "previous": s_prev,
        "deltas": {
            k: metrics.delta(s_cur[k], s_prev[k])
            for k in ("total", "outside_window", "emergency", "median_lead_hours", "median_resolution_hours", "open")
        },
        "breakdowns": metrics.breakdowns(cur, window),
        "trend": metrics.breakdowns(trend, window)["weekly"],
        "notable": metrics.notable(cur, window),
        "changes": sorted(cur, key=lambda c: c.ref_date),
        "commentary": commentary(s_cur, s_prev, metrics.breakdowns(cur, window)),
        "outcomes": OUTCOMES,
    }


def _n(v) -> str:
    """Türkçe ondalık: 40.0 -> 40, 42.5 -> 42,5"""
    return f"{v:g}".replace(".", ",") if isinstance(v, float) else str(v)


def commentary(cur: dict, prev: dict, bd: dict) -> list[str]:
    """Kural tabanlı kısa yorumlar (rapora düz metin olarak girer)."""
    lines: list[str] = []
    if cur["total"] == 0:
        return ["Bu hafta kayıtlı deployment talebi yok."]
    diff = cur["total"] - prev["total"]
    if prev["total"]:
        trend = "arttı" if diff > 0 else "azaldı" if diff < 0 else "değişmedi"
        lines.append(f"Bu hafta {cur['total']} deployment talebi var; geçen haftaya göre {abs(diff)} adet {trend}." if diff else
                     f"Bu hafta {cur['total']} deployment talebi var; geçen haftayla aynı.")
    else:
        lines.append(f"Bu hafta {cur['total']} deployment talebi var.")
    if bd["request_type"]:
        top = bd["request_type"][0]
        lines.append(f"En sık talep tipi: {top['label']} ({top['value']} adet).")
    apps = [a for a in bd["application"] if a["label"] not in ("Belirtilmemiş", "Diğer")]
    if apps:
        lines.append(f"En çok değişen uygulama: {apps[0]['label']} ({apps[0]['value']} talep).")
    if cur["outside_window"]:
        lines.append(
            f"{cur['outside_window']} talep (%{_n(cur['outside_window_rate'])}) bakım penceresi dışında planlanmış."
        )
    if cur["retroactive"]:
        lines.append(f"{cur['retroactive']} talepte deploy tarihi, talebin açılışından önce; kayıt iş yapıldıktan sonra açılmış görünüyor.")
    if cur["short_notice_rate"] is not None and cur["short_notice_rate"] >= 50:
        lines.append(f"Taleplerin %{_n(cur['short_notice_rate'])}'i deploy'dan 24 saatten kısa süre önce açılmış.")
    if cur["emergency"]:
        lines.append(f"{cur['emergency']} acil/kritik deployment var.")
    if cur["no_pre_test"] or cur["no_post_test"]:
        lines.append(
            f"Test yapılamayan talepler: deploy öncesi {cur['no_pre_test']}, deploy sonrası {cur['no_post_test']}."
        )
    if cur["db_structural"]:
        lines.append(f"{cur['db_structural']} talepte veritabanında yapısal değişiklik var.")
    if cur["open"]:
        lines.append(f"{cur['open']} talep hâlâ kapanmamış.")
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
