from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

# Sabit sözlükler: arayüz, Jira eşlemesi ve metrikler hep bu değerleri kullanır.
CHANGE_TYPES = {"standard": "Standart", "normal": "Normal", "emergency": "Acil"}
STATUSES = {
    "planned": "Planlandı",
    "success": "Başarılı",
    "failed": "Başarısız",
    "rolled_back": "Geri alındı",
    "cancelled": "İptal",
}
ENVIRONMENTS = {"prod": "Prod", "preprod": "Pre-prod", "test": "Test"}
RISKS = {"low": "Düşük", "medium": "Orta", "high": "Yüksek"}


class ChangeRequest(Base):
    __tablename__ = "change_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    jira_key: Mapped[str | None] = mapped_column(String(32), unique=True, index=True)
    source: Mapped[str] = mapped_column(String(16), default="manual")  # jira | manual | csv

    summary: Mapped[str] = mapped_column(String(500))
    change_type: Mapped[str] = mapped_column(String(16), default="normal", index=True)
    status: Mapped[str] = mapped_column(String(16), default="planned", index=True)
    environment: Mapped[str] = mapped_column(String(16), default="prod", index=True)
    application: Mapped[str] = mapped_column(String(120), default="Bilinmiyor", index=True)
    team: Mapped[str] = mapped_column(String(120), default="Bilinmiyor", index=True)
    requester: Mapped[str | None] = mapped_column(String(120))
    risk: Mapped[str | None] = mapped_column(String(16))
    description: Mapped[str | None] = mapped_column(Text)

    # Tüm zamanlar yerel saat (TIMEZONE) olarak, tz bilgisi olmadan tutulur.
    requested_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime)
    deployed_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    @property
    def ref_date(self) -> datetime:
        """Raporlamada kaydın hangi haftaya düşeceğini belirleyen tarih."""
        return self.deployed_at or self.requested_at
