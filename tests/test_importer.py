from datetime import datetime

from vdeploy import importer
from vdeploy.jira_client import _flatten, issue_to_fields

from .sample import csv_bytes

CLOSED = {"kapalı"}


def test_csv_rows_map_to_records():
    recs = [importer.to_record(r, CLOSED) for r in importer.rows_from_csv(csv_bytes())]
    a, b = recs
    assert a["jira_key"] == "SAY-1"
    assert a["application"] == "UygA"  # (ITYE-..) eki temizlenir
    assert a["microservices"] == "svc-a, svc-b"  # tekrarlanan sütunlar birleşir
    assert a["deploy_planned"] == datetime(2026, 10, 8, 19, 0)
    assert a["is_closed"] and not a["is_emergency"]
    assert a["db_structural_change"] is False
    assert b["is_emergency"] and not b["is_closed"]
    assert b["resolved"] is None and b["department"] is None
    assert b["pre_test_possible"] is False


def test_empty_markers_and_dates():
    assert importer.clean("'-") is None
    assert importer.clean(" Vcollect (ITYE-113462) ") == "Vcollect"
    assert importer.parse_dt("2026-10-08T16:00:00.000+0000") == datetime(2026, 10, 8, 19, 0)  # İstanbul
    assert importer.parse_dt("08/Oct/26 7:00 PM") == datetime(2026, 10, 8, 19, 0)


def test_jira_issue_uses_display_names():
    issue = {
        "key": "SAY-9",
        "fields": {
            "summary": "Deploy",
            "status": {"name": "Kapalı"},
            "created": "2026-10-08T10:00:00.000+0300",
            "customfield_1": "2026-10-08T19:00:00.000+0300",
            "customfield_2": {"requestType": {"name": "Kubernetes Deployment"}},
            "customfield_3": ["svc-a (ITYE-1)", "svc-b (ITYE-2)"],
            "customfield_4": {"value": "Evet"},
        },
    }
    names = {"customfield_1": "Deployment Tarihi", "customfield_2": "Customer Request Type",
             "customfield_3": "Microservisler", "customfield_4": "Deployment Öncesi Test Yapılabilir?"}
    rec = importer.to_record(importer.canonicalize(issue_to_fields(issue, names)), CLOSED)
    assert rec["request_type"] == "Kubernetes Deployment"
    assert rec["deploy_planned"] == datetime(2026, 10, 8, 19, 0)
    assert rec["microservices"] == "svc-a, svc-b"
    assert rec["pre_test_possible"] is True and rec["is_closed"]


def test_flatten_bool_before_int():
    assert _flatten(True) == ["Evet"]
