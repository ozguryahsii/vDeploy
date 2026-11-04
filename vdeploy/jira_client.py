"""Jira Data Center / Server REST API v2 istemcisi (Personal Access Token ile)."""
from __future__ import annotations

from collections import defaultdict

import httpx
from sqlalchemy.orm import Session

from . import importer, settings_store
from .models import SyncLog

PAGE_SIZE = 100


def _flatten(value) -> list[str]:
    """Jira alan değerini düz metin listesine çevirir (kullanıcı, seçim, Assets nesnesi...)."""
    if value is None:
        return []
    if isinstance(value, bool):
        return ["Evet" if value else "Hayır"]
    if isinstance(value, (str, int, float)):
        return [str(value)]
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            out.extend(_flatten(item))
        return out
    if isinstance(value, dict):
        if "requestType" in value:  # Service Management "Customer Request Type"
            return _flatten(value["requestType"].get("name"))
        for k in ("name", "value", "label", "displayName", "objectKey"):
            if k in value and value[k] not in (None, ""):
                # Kullanıcı alanlarında kullanıcı adı (name) CSV ile aynı biçimde
                return [str(value[k])]
    return []


def issue_to_fields(issue: dict, names: dict[str, str]) -> dict[str, list[str]]:
    fields: dict[str, list[str]] = defaultdict(list)
    fields["key"].append(issue.get("key", ""))
    for fid, value in (issue.get("fields") or {}).items():
        fields[names.get(fid, fid)].extend(_flatten(value))
        fields[fid].extend(_flatten(value))  # sistem alanları id ile de eşleşsin (summary, status...)
    return fields


class JiraClient:
    def __init__(self, base_url: str, pat: str, verify: bool = True, timeout: float = 30.0):
        if not base_url or not pat:
            raise ValueError("Jira adresi ve Personal Access Token tanımlı olmalı (Ayarlar > Jira).")
        self.client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {pat}", "Accept": "application/json"},
            verify=verify,
            timeout=timeout,
        )

    def myself(self) -> dict:
        r = self.client.get("/rest/api/2/myself")
        r.raise_for_status()
        return r.json()

    def search(self, jql: str):
        start = 0
        while True:
            r = self.client.get(
                "/rest/api/2/search",
                params={"jql": jql, "startAt": start, "maxResults": PAGE_SIZE, "fields": "*all", "expand": "names"},
            )
            r.raise_for_status()
            data = r.json()
            names = data.get("names", {})
            issues = data.get("issues", [])
            for issue in issues:
                yield issue, names
            start += len(issues)
            if not issues or start >= data.get("total", 0):
                break


def client_from_settings(values: dict[str, str]) -> JiraClient:
    return JiraClient(
        values["jira.base_url"],
        values["jira.pat"],
        verify=settings_store.truthy(values["jira.verify_ssl"]),
    )


def sync(db: Session, jql: str | None = None) -> SyncLog:
    values = settings_store.get_all(db)
    closed = {s.strip().casefold() for s in values["jira.closed_statuses"].split(",") if s.strip()}
    log = SyncLog(kind="jira")
    try:
        client = client_from_settings(values)
        records = []
        for issue, names in client.search(jql or values["jira.jql"]):
            row = importer.canonicalize(issue_to_fields(issue, names))
            rec = importer.to_record(row, closed)
            if rec:
                records.append(rec)
        log.inserted, log.updated = importer.upsert(db, records, "jira")
        log.message = f"{len(records)} kayıt işlendi."
    except Exception as exc:  # ekranda ve logda gösterilsin
        db.rollback()
        log.ok = False
        log.message = f"{type(exc).__name__}: {exc}"
    db.add(log)
    db.commit()
    return log
