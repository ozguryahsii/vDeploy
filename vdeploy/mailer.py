from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage

from . import settings_store


def send(values: dict[str, str], subject: str, html: str, to: list[str] | None = None,
         attachments: list[tuple[str, bytes, str]] | None = None) -> list[str]:
    host = values["smtp.host"].strip()
    if not host:
        raise ValueError("SMTP sunucusu tanımlı değil (Ayarlar > E-posta).")
    recipients = to or [x.strip() for x in values["smtp.to"].replace(";", ",").split(",") if x.strip()]
    if not recipients:
        raise ValueError("Alıcı tanımlı değil (Ayarlar > E-posta).")
    sender = values["smtp.from"].strip() or values["smtp.user"].strip()
    if not sender:
        raise ValueError("Gönderen adresi tanımlı değil (Ayarlar > E-posta).")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg.set_content("Bu e-posta HTML formatındadır.")
    msg.add_alternative(html, subtype="html")
    for name, data, mime in attachments or []:
        maintype, subtype = mime.split("/", 1)
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=name)

    port = int(values["smtp.port"] or 25)
    security = values["smtp.security"]
    context = ssl.create_default_context()
    if security == "ssl":
        server: smtplib.SMTP = smtplib.SMTP_SSL(host, port, timeout=30, context=context)
    else:
        server = smtplib.SMTP(host, port, timeout=30)
    with server:
        if security == "starttls":
            server.starttls(context=context)
        if values["smtp.user"].strip():
            server.login(values["smtp.user"].strip(), values["smtp.password"])
        server.send_message(msg)
    return recipients


def is_configured(values: dict[str, str]) -> bool:
    return bool(values["smtp.host"].strip() and values["smtp.to"].strip())


__all__ = ["send", "is_configured", "settings_store"]
