from datetime import datetime, time

from vdeploy import metrics
from vdeploy.models import ChangeRequest
from vdeploy.settings_store import Window

THU_EVENING = Window(days=frozenset({3}), start=time(18, 0), end=time(23, 59))


def cr(created, planned=None, **kw):
    return ChangeRequest(created=created, deploy_planned=planned, request_type=kw.pop("request_type", "K8s"),
                         is_closed=kw.pop("is_closed", True), is_emergency=kw.pop("is_emergency", False),
                         outcome=kw.pop("outcome", "unknown"), **kw)


def test_window_and_overnight_window():
    assert THU_EVENING.contains(datetime(2026, 10, 8, 19, 0))
    assert not THU_EVENING.contains(datetime(2026, 10, 8, 14, 0))
    assert not THU_EVENING.contains(datetime(2026, 10, 9, 19, 0))
    night = Window(days=frozenset({0}), start=time(22, 0), end=time(6, 0))
    assert night.contains(datetime(2026, 10, 5, 23, 0)) and night.contains(datetime(2026, 10, 5, 2, 0))


def test_summary_counts():
    rows = [
        cr(datetime(2026, 10, 8, 10), datetime(2026, 10, 8, 19)),  # içeride, 9 sa
        cr(datetime(2026, 10, 8, 14), datetime(2026, 10, 8, 13)),  # geriye dönük, dışarıda
        cr(datetime(2026, 10, 6, 9), datetime(2026, 10, 9, 15), is_emergency=True, outcome="rolled_back",
           is_closed=False),
        cr(datetime(2026, 10, 6, 9), datetime(2026, 10, 8, 20), outcome="success"),
    ]
    s = metrics.summary(rows, THU_EVENING)
    assert s["total"] == 4 and s["open"] == 1 and s["emergency"] == 1
    assert s["outside_window"] == 2 and s["outside_window_rate"] == 50.0
    assert s["retroactive"] == 1
    assert s["change_failure_rate"] == 50.0


def test_weekly_breakdown_fills_gaps():
    rows = [cr(datetime(2026, 10, 1), datetime(2026, 10, 1, 19)), cr(datetime(2026, 10, 20), datetime(2026, 10, 22, 19))]
    w = metrics.breakdowns(rows, THU_EVENING)["weekly"]
    assert w["labels"] == ["28.09", "05.10", "12.10", "19.10"]
    assert w["totals"] == [1, 0, 0, 1]
