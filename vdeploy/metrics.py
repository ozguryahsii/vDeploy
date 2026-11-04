"""Dashboard ve rapor metrikleri. Haftalık hacim küçük olduğu için hesaplar
Python tarafında, seçilen tarih aralığındaki kayıtlar üzerinden yapılır."""
from __future__ import annotations

import statistics
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from .models import OUTCOMES, ChangeRequest
from .settings_store import Window

LEAD_BUCKETS = [
    ("Geriye dönük", None, 0),
    ("0–4 saat", 0, 4),
    ("4–24 saat", 4, 24),
    ("1–3 gün", 24, 72),
    ("3+ gün", 72, None),
]
TOP_N = 10


def week_start(d: date | datetime) -> date:
    d = d.date() if isinstance(d, datetime) else d
    return d - timedelta(days=d.weekday())


def deploy_time(c: ChangeRequest) -> datetime | None:
    return c.deploy_planned or c.resolved


def lead_hours(c: ChangeRequest) -> float | None:
    """Talep açılışından planlanan deploy'a kadar geçen süre (saat)."""
    if not c.deploy_planned:
        return None
    return (c.deploy_planned - c.created).total_seconds() / 3600


def resolution_hours(c: ChangeRequest) -> float | None:
    if not c.resolved:
        return None
    return (c.resolved - c.created).total_seconds() / 3600


def outside_window(c: ChangeRequest, window: Window) -> bool:
    t = deploy_time(c)
    return t is not None and not window.contains(t)


def _top(counter: Counter, n: int = TOP_N) -> list[dict]:
    items = counter.most_common()
    head = [{"label": k, "value": v} for k, v in items[:n]]
    rest = sum(v for _, v in items[n:])
    if rest:
        head.append({"label": "Diğer", "value": rest})
    return head


def _median(values: list[float]) -> float | None:
    return round(statistics.median(values), 1) if values else None


def _rate(part: int, whole: int) -> float | None:
    return round(100 * part / whole, 1) if whole else None


@dataclass
class Period:
    start: date
    end: date  # dahil

    def contains(self, d: datetime) -> bool:
        return self.start <= d.date() <= self.end


def in_period(changes: list[ChangeRequest], period: Period) -> list[ChangeRequest]:
    return [c for c in changes if period.contains(c.ref_date)]


def summary(changes: list[ChangeRequest], window: Window) -> dict:
    total = len(changes)
    outside = [c for c in changes if outside_window(c, window)]
    leads = [h for h in (lead_hours(c) for c in changes) if h is not None]
    resolutions = [h for h in (resolution_hours(c) for c in changes) if h is not None]
    outcomes = Counter(c.outcome for c in changes)
    judged = outcomes["success"] + outcomes["failed"] + outcomes["rolled_back"]
    return {
        "total": total,
        "closed": sum(c.is_closed for c in changes),
        "open": sum(not c.is_closed for c in changes),
        "emergency": sum(c.is_emergency for c in changes),
        "outside_window": len(outside),
        "outside_window_rate": _rate(len(outside), total),
        "retroactive": sum(1 for h in leads if h < 0),
        "short_notice": sum(1 for h in leads if 0 <= h < 24),
        "short_notice_rate": _rate(sum(1 for h in leads if h < 24), len(leads)),
        "median_lead_hours": _median(leads),
        "median_resolution_hours": _median(resolutions),
        "db_structural": sum(1 for c in changes if c.db_structural_change),
        "no_pre_test": sum(1 for c in changes if c.pre_test_possible is False),
        "no_post_test": sum(1 for c in changes if c.post_test_possible is False),
        "vendor": sum(1 for c in changes if c.vendor),
        "outcomes": {k: outcomes.get(k, 0) for k in OUTCOMES},
        "outcome_judged": judged,
        "change_failure_rate": _rate(outcomes["failed"] + outcomes["rolled_back"], judged),
        "applications": len({c.application for c in changes if c.application}),
        "microservices": len({m for c in changes for m in c.microservice_list}),
    }


def breakdowns(changes: list[ChangeRequest], window: Window) -> dict:
    types = Counter(c.request_type for c in changes)
    type_order = [k for k, _ in types.most_common()]

    weeks: dict[date, Counter] = {}
    weeks_outside: Counter = Counter()
    for c in changes:
        w = week_start(c.ref_date)
        weeks.setdefault(w, Counter())[c.request_type] += 1
        if outside_window(c, window):
            weeks_outside[w] += 1
    if weeks:
        w, last = min(weeks), max(weeks)
        while w <= last:  # boş haftalar da grafikte görünsün
            weeks.setdefault(w, Counter())
            w += timedelta(days=7)
    week_keys = sorted(weeks)

    heat = [[0] * 24 for _ in range(7)]
    for c in changes:
        t = deploy_time(c)
        if t:
            heat[t.weekday()][t.hour] += 1

    lead_counts = Counter()
    for c in changes:
        h = lead_hours(c)
        if h is None:
            continue
        for label, lo, hi in LEAD_BUCKETS:
            if (lo is None or h >= lo) and (hi is None or h < hi):
                lead_counts[label] += 1
                break

    return {
        "weekly": {
            "labels": [w.strftime("%d.%m") for w in week_keys],
            "week_starts": [w.isoformat() for w in week_keys],
            "series": [{"label": t, "values": [weeks[w][t] for w in week_keys]} for t in type_order],
            "outside": [weeks_outside[w] for w in week_keys],
            "totals": [sum(weeks[w].values()) for w in week_keys],
        },
        "request_type": _top(types),
        "application": _top(Counter(c.application or "Belirtilmemiş" for c in changes)),
        "microservice": _top(Counter(m for c in changes for m in c.microservice_list)),
        "department": _top(Counter(c.department or "Belirtilmemiş" for c in changes)),
        "assignee": _top(Counter(c.assignee or "Atanmamış" for c in changes)),
        "requester": _top(Counter(c.requester or "—" for c in changes)),
        "heatmap": heat,
        "lead_buckets": [{"label": label, "value": lead_counts.get(label, 0)} for label, _, _ in LEAD_BUCKETS],
    }


def notable(changes: list[ChangeRequest], window: Window) -> list[dict]:
    """Rapor ve dashboard'da dikkat çekilecek kayıtlar ve nedenleri."""
    out = []
    for c in sorted(changes, key=lambda x: x.ref_date):
        reasons = []
        if c.is_emergency:
            reasons.append("Acil")
        if c.outcome in ("failed", "rolled_back"):
            reasons.append(OUTCOMES[c.outcome])
        if outside_window(c, window):
            reasons.append("Pencere dışı")
        h = lead_hours(c)
        if h is not None and h < 0:
            reasons.append("Geriye dönük kayıt")
        if c.db_structural_change:
            reasons.append("DB yapısal değişiklik")
        if c.pre_test_possible is False or c.post_test_possible is False:
            reasons.append("Test yapılamıyor")
        if not c.is_closed:
            reasons.append("Açık")
        if reasons:
            out.append({"change": c, "reasons": reasons})
    return out


def delta(current: float | None, previous: float | None) -> dict:
    if current is None or previous is None:
        return {"diff": None, "direction": "flat"}
    diff = round(current - previous, 1)
    return {"diff": diff, "direction": "up" if diff > 0 else "down" if diff < 0 else "flat"}
