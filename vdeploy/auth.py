"""Active Directory (LDAP) ile giriş.

Varsayılan olarak KAPALI: Ayarlar > Active Directory ekranından "AD ile giriş
zorunlu" işaretlenene kadar herkes doğrudan girer. Açıldığında kullanıcı
`kullanici@domain` (UPN) ile LDAP bind yapılarak doğrulanır; isteğe bağlı
olarak belirli bir AD grubuna üyelik aranır.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import settings_store


@dataclass
class AuthResult:
    ok: bool
    username: str = ""
    display_name: str = ""
    error: str = ""


def enabled(values: dict[str, str]) -> bool:
    return settings_store.truthy(values["ad.enabled"]) and bool(values["ad.server"].strip())


def _escape(value: str) -> str:
    from ldap3.utils.conv import escape_filter_chars

    return escape_filter_chars(value)


def authenticate(values: dict[str, str], username: str, password: str) -> AuthResult:
    username = username.strip()
    if not username or not password:
        return AuthResult(False, error="Kullanıcı adı ve parola gerekli.")
    try:
        from ldap3 import ALL, Connection, Server
        from ldap3.core.exceptions import LDAPBindError, LDAPException
    except ImportError:
        return AuthResult(False, error="ldap3 paketi kurulu değil.")

    sam = username.split("\\")[-1].split("@")[0]
    domain = values["ad.domain"].strip()
    upn = username if "@" in username else (f"{sam}@{domain}" if domain else sam)
    server = Server(
        values["ad.server"].strip(),
        port=int(values["ad.port"] or 636),
        use_ssl=settings_store.truthy(values["ad.use_ssl"]),
        get_info=ALL,
        connect_timeout=10,
    )
    try:
        conn = Connection(server, user=upn, password=password, auto_bind=True, receive_timeout=10)
    except LDAPBindError:
        return AuthResult(False, error="Kullanıcı adı veya parola hatalı.")
    except LDAPException as exc:
        return AuthResult(False, error=f"AD sunucusuna bağlanılamadı: {exc}")

    display = sam
    base_dn = values["ad.base_dn"].strip()
    group = values["ad.allowed_group"].strip()
    try:
        if base_dn:
            conn.search(base_dn, f"(sAMAccountName={_escape(sam)})", attributes=["displayName", "memberOf"])
            if conn.entries:
                entry = conn.entries[0]
                display = str(entry.displayName) if "displayName" in entry and entry.displayName.value else sam
                if group:
                    member_of = [str(g).casefold() for g in (entry.memberOf.values if "memberOf" in entry else [])]
                    if group.casefold() not in member_of and not any(
                        g.startswith(f"cn={group.casefold()},") for g in member_of
                    ):
                        return AuthResult(False, error="Bu uygulamaya erişim yetkiniz yok (AD grubu).")
        elif group:
            return AuthResult(False, error="Grup kontrolü için Base DN tanımlanmalı.")
    finally:
        conn.unbind()
    return AuthResult(True, username=sam, display_name=display)


def test_connection(values: dict[str, str], username: str, password: str) -> AuthResult:
    return authenticate(values, username, password)
