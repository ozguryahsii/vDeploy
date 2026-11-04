import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("VDEPLOY_SECRET_KEY", "test")
    from vdeploy import config, db

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DATABASE_URL", f"sqlite:///{tmp_path / 't.db'}")
    monkeypatch.setattr(config, "SCHEDULER_ENABLED", False)
    from vdeploy.web import app

    with TestClient(app) as c:
        yield c
    db.SessionLocal.configure(bind=None)
