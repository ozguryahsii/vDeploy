from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

# Jira'da sonuç alanı yok; bu değer uygulama içinden işaretlenir.
OUTCOMES = {
    "unknown": "Belirtilmedi",
    "success": "Başarılı",
    "failed": "Başarısız",
    "rolled_back": "Geri alındı",
    "cancelled": "İptal",
}


class ChangeRequest(Base):
    __tablename__ = "change_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    jira_key: Mapped[str | None] = mapped_column(String(32), unique=True, index=True)
    source: Mapped[str] = mapped_column(String(16), default="manual")  # csv | jira | manual

    summary: Mapped[str] = mapped_column(String(500), default="")
    request_type: Mapped[str] = mapped_column(String(120), default="Diğer", index=True)
    status: Mapped[str] = mapped_column(String(80), default="")
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False)

    requester: Mapped[str | None] = mapped_column(String(120))
    assignee: Mapped[str | None] = mapped_column(String(120))
    department: Mapped[str | None] = mapped_column(String(160))
    application: Mapped[str | None] = mapped_column(String(160), index=True)
    microservices: Mapped[str | None] = mapped_column(Text)  # virgülle ayrılmış
    database: Mapped[str | None] = mapped_column(String(160))
    db_type: Mapped[str | None] = mapped_column(String(60))
    db_structural_change: Mapped[bool | None] = mapped_column(Boolean)
    vendor: Mapped[str | None] = mapped_column(String(120))
    vendor_ticket: Mapped[str | None] = mapped_column(String(60))
    tag: Mapped[str | None] = mapped_column(String(200))

    is_emergency: Mapped[bool] = mapped_column(Boolean, default=False)
    emergency_reason: Mapped[str | None] = mapped_column(Text)
    pre_test_possible: Mapped[bool | None] = mapped_column(Boolean)
    post_test_possible: Mapped[bool | None] = mapped_column(Boolean)

    outcome: Mapped[str] = mapped_column(String(16), default="unknown")
    notes: Mapped[str | None] = mapped_column(Text)

    # Yerel saat (Europe/Istanbul), tz bilgisi olmadan.
    created: Mapped[datetime] = mapped_column(DateTime, index=True)
    deploy_planned: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    resolved: Mapped[datetime | None] = mapped_column(DateTime)

    inserted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    @property
    def ref_date(self) -> datetime:
        """Kaydın hangi haftaya sayılacağı: planlanan deploy, yoksa çözüm, yoksa oluşturma."""
        return self.deploy_planned or self.resolved or self.created

    @property
    def microservice_list(self) -> list[str]:
        return [m.strip() for m in (self.microservices or "").split(",") if m.strip()]


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")


class SyncLog(Base):
    __tablename__ = "sync_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    kind: Mapped[str] = mapped_column(String(20))  # csv | jira | mail
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    inserted: Mapped[int] = mapped_column(Integer, default=0)
    updated: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str] = mapped_column(Text, default="")
