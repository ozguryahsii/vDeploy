from vdeploy import report


def _summary(**kw):
    base = dict(total=3, closed=3, open=0, outside_window=0, outside_window_rate=0.0, retroactive=0,
                short_notice_rate=None, median_resolution_hours=None, emergency=0, no_pre_test=0, no_post_test=0,
                db_structural=0, vendor=0, change_failure_rate=None, outcome_judged=0)
    base.update(kw)
    return base


def _bd(apps):
    return {"request_type": [], "application": apps, "microservice": [], "department": []}


def test_top_application_only_when_two_or_more():
    lines = report.commentary(_summary(), _bd([{"label": "Vjoin", "value": 1}, {"label": "Porta", "value": 1}]))
    assert not any("uygulama" in l for l in lines)
    lines = report.commentary(_summary(), _bd([{"label": "Vcollect", "value": 2}, {"label": "Vjoin", "value": 1}]))
    assert "En çok deploy çıkan uygulama: Vcollect (2)." in lines


def test_ties_listed_and_unspecified_skipped():
    rows = [{"label": "Belirtilmemiş", "value": 5}, {"label": "Vjoin", "value": 2}, {"label": "Porta", "value": 2}]
    lines = report.commentary(_summary(), _bd(rows))
    assert "En çok deploy çıkan uygulama: Vjoin ve Porta (2'er)." in lines


def test_no_week_over_week_statement():
    text = " ".join(report.commentary(_summary(), _bd([])))
    assert "geçen hafta" not in text and "arttı" not in text and "azaldı" not in text
