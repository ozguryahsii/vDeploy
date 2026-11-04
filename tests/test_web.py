from .sample import csv_bytes


def test_pages_after_csv_import(client):
    r = client.post("/import/csv", files={"file": ("export.csv", csv_bytes(), "text/csv")}, follow_redirects=False)
    assert r.status_code == 303
    assert "2 yeni" in client.get("/import").text
    for url in ["/?range=all", "/changes", "/changes/1", "/changes/new", "/report?week=2026-10-05",
                "/settings?tab=smtp", "/settings?tab=jira", "/settings?tab=window", "/settings?tab=schedule",
                "/settings?tab=ad"]:
        assert client.get(url).status_code == 200, url
    html = client.get("/report/download.html?week=2026-10-05")
    assert "attachment" in html.headers["content-disposition"] and "SAY-1" in html.text
    assert "SAY-1" in client.get("/report/download.csv?week=2026-10-05").content.decode("utf-8-sig")


def test_outcome_survives_reimport(client):
    client.post("/import/csv", files={"file": ("e.csv", csv_bytes(), "text/csv")})
    client.post("/changes/1", data={"outcome": "rolled_back", "notes": "geri alındı"})
    client.post("/import/csv", files={"file": ("e.csv", csv_bytes(), "text/csv")})
    page = client.get("/changes/1").text
    assert 'value="rolled_back" selected' in page and "geri alındı" in page


def test_manual_entry(client):
    r = client.post("/changes/new", data={"summary": "Elle giriş", "request_type": "IIS Deployment",
                                          "created": "2026-10-15T10:00", "deploy_planned": "2026-10-15T19:00",
                                          "outcome": "success"}, follow_redirects=False)
    assert r.status_code == 303
    assert "Elle giriş" in client.get("/changes").text


def test_settings_secret_kept_when_blank(client):
    client.post("/settings/smtp", data={"smtp.host": "relay", "smtp.port": "25", "smtp.security": "none",
                                        "smtp.password": "gizli", "smtp.to": "a@b.c"})
    client.post("/settings/smtp", data={"smtp.host": "relay2", "smtp.port": "25", "smtp.security": "none",
                                        "smtp.password": "", "smtp.to": "a@b.c"})
    from vdeploy import settings_store
    from vdeploy.db import SessionLocal

    with SessionLocal() as db:
        assert settings_store.get(db, "smtp.password") == "gizli"
        assert settings_store.get(db, "smtp.host") == "relay2"


def test_ad_login_off_by_default_and_enforced_when_on(client):
    assert client.get("/", follow_redirects=False).status_code == 200
    client.post("/settings/ad", data={"ad.enabled": "1", "ad.server": "dc.local", "ad.port": "636"})
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/login")
    assert client.get("/login").status_code == 200


def test_list_filters_from_chart_clicks(client):
    client.post("/import/csv", files={"file": ("e.csv", csv_bytes(), "text/csv")})
    page = client.get("/changes?start=2026-10-05&end=2026-10-11&application=UygA").text
    assert "SAY-1" in page and "SAY-2" not in page and "Tümünü temizle" in page
    page = client.get("/changes?department=__none__").text
    assert "SAY-2" in page and "SAY-1</a>" not in page
    page = client.get("/changes?microservice=svc-b&only=inside").text
    assert "SAY-1" in page and "SAY-2" not in page
    page = client.get("/changes?dow=1&hour=11").text  # Salı 11:00
    assert "SAY-2" in page and "SAY-1</a>" not in page


def test_report_standalone_embeds_assets(client):
    client.post("/import/csv", files={"file": ("e.csv", csv_bytes(), "text/csv")})
    html = client.get("/report/download.html?week=2026-10-05").text
    assert "Chart.js v4" in html and "VDEPLOY_REPORT" in html and "interactive = false" in html
    assert "/static/" not in html
