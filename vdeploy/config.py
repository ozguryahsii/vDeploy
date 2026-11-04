"""Ortam ayarları. Uygulama içi ayarlar (SMTP, Jira, AD, bakım penceresi)
veritabanında tutulur ve Ayarlar ekranından yönetilir; burada yalnızca
uygulamanın ayağa kalkması için gerekenler var."""
from __future__ import annotations

import os
import secrets
from pathlib import Path

DATA_DIR = Path(os.environ.get("VDEPLOY_DATA_DIR", Path.cwd() / "data")).resolve()
DATABASE_URL = os.environ.get("VDEPLOY_DATABASE_URL", f"sqlite:///{DATA_DIR / 'vdeploy.db'}")
TIMEZONE = os.environ.get("VDEPLOY_TIMEZONE", "Europe/Istanbul")
SCHEDULER_ENABLED = os.environ.get("VDEPLOY_SCHEDULER", "1") not in {"0", "false", "no"}


def secret_key() -> str:
    """Oturum çerezi için anahtar; ilk çalışmada üretilip data/ altında saklanır."""
    env = os.environ.get("VDEPLOY_SECRET_KEY")
    if env:
        return env
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / ".secret_key"
    if not path.exists():
        path.write_text(secrets.token_urlsafe(48))
        path.chmod(0o600)
    return path.read_text().strip()
