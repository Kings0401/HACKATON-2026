"""Acceso a datos. SupabaseRepository usa la credencial de servidor (omite RLS),
por eso las reglas se revalidan explícitamente en services/access.py.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

import httpx

from .config import Settings

log = logging.getLogger(__name__)


class Repository(Protocol):
    simulated: bool

    def persona(self, persona_id: str) -> dict | None: ...
    def persona_by_code(self, code: str) -> dict | None: ...
    def persona_by_auth(self, auth_user_id: str) -> dict | None: ...
    def credential_by_hash(self, token_hash: str) -> dict | None: ...
    def membership(self, persona_id: str) -> dict | None: ...
    def reservations(self, persona_id: str) -> list[dict]: ...
    def invitation_by_code(self, code: str) -> dict | None: ...
    def invitations(self, persona_id: str) -> list[dict]: ...
    def permit_by_code(self, code: str) -> dict | None: ...
    def permits(self, persona_id: str) -> list[dict]: ...
    def insert(self, table: str, row: dict) -> dict: ...
    def update(self, table: str, key: str, value: Any, values: dict) -> None: ...
    def upsert(self, table: str, row: dict) -> None: ...
    def recent(self, table: str, limit: int = 20, **filters: Any) -> list[dict]: ...
    def one(self, table: str, column: str, value: Any) -> dict | None: ...
    def face_folders(self) -> list[str]: ...
    def face_files(self, persona_id: str) -> list[str]: ...
    def download_face(self, persona_id: str, name: str) -> bytes: ...
    def upload_face(self, persona_id: str, name: str, content: bytes, mime: str) -> None: ...
    def delete(self, table: str, key: str, value: Any) -> None: ...
    def revoke_credentials(self, persona_id: str, when: str) -> None: ...
    def upload(self, bucket: str, path: str, content: bytes, mime: str) -> None: ...
    def signed_url(self, bucket: str, path: str, ttl: int) -> str | None: ...
    def auth_user_id(self, jwt: str) -> str | None: ...
    def broadcast(self, topic: str, event: str, payload: dict) -> None: ...


class StorageNotFound(LookupError):
    pass


class SupabaseRepository:
    simulated = False

    def __init__(self, settings: Settings):
        from supabase import create_client

        self.settings = settings
        self.client = create_client(settings.supabase_url, settings.supabase_secret_key)
        self.http = httpx.Client(timeout=5)

    # ---------- consultas de negocio ----------

    def one(self, table: str, column: str, value: Any) -> dict | None:
        data = self.client.table(table).select("*").eq(column, value).limit(1).execute().data
        return data[0] if data else None

    def persona(self, persona_id: str) -> dict | None:
        return self.one("personas", "id", persona_id)

    def persona_by_code(self, code: str) -> dict | None:
        return self.one("personas", "codigo_credencial", code)

    def persona_by_auth(self, auth_user_id: str) -> dict | None:
        return self.one("personas", "auth_user_id", auth_user_id)

    def credential_by_hash(self, token_hash: str) -> dict | None:
        return self.one("credenciales", "token_hash", token_hash)

    def membership(self, persona_id: str) -> dict | None:
        return self.one("membresias", "persona_id", persona_id)

    def reservations(self, persona_id: str) -> list[dict]:
        return (
            self.client.table("reservas")
            .select("*")
            .eq("persona_id", persona_id)
            .eq("estado", "CONFIRMADA")
            .execute()
            .data
        )

    def invitation_by_code(self, code: str) -> dict | None:
        return self.one("invitaciones", "codigo_qr", code)

    def invitations(self, persona_id: str) -> list[dict]:
        return self.client.table("invitaciones").select("*").eq("persona_id", persona_id).execute().data

    def permit_by_code(self, code: str) -> dict | None:
        return self.one("permisos_laborales", "codigo_autorizacion", code)

    def permits(self, persona_id: str) -> list[dict]:
        return (
            self.client.table("permisos_laborales").select("*").eq("persona_id", persona_id).execute().data
        )

    # ---------- registro ----------

    def insert(self, table: str, row: dict) -> dict:
        data = self.client.table(table).insert(row).execute().data
        return data[0] if data else row

    def update(self, table: str, key: str, value: Any, values: dict) -> None:
        self.client.table(table).update(values).eq(key, value).execute()

    def upsert(self, table: str, row: dict) -> None:
        self.client.table(table).upsert(row).execute()

    def recent(self, table: str, limit: int = 20, **filters: Any) -> list[dict]:
        query = self.client.table(table).select("*")
        for column, value in filters.items():
            query = query.eq(column, value)
        return query.order("created_at", desc=True).limit(limit).execute().data

    # ---------- Storage privado ----------

    def face_folders(self) -> list[str]:
        items = self.client.storage.from_(self.settings.faces_bucket).list()
        # Las carpetas no tienen id; los archivos sueltos en la raíz se ignoran.
        return sorted(i["name"] for i in items if i.get("id") is None and not i["name"].startswith("."))

    def face_files(self, persona_id: str) -> list[str]:
        items = self.client.storage.from_(self.settings.faces_bucket).list(
            path=persona_id, options={"limit": 1000}
        )
        return sorted(
            i["name"]
            for i in items
            if i.get("id") is not None and i["name"].lower().endswith((".jpg", ".jpeg", ".png"))
        )

    def download_face(self, persona_id: str, name: str) -> bytes:
        from storage3.exceptions import StorageApiError

        try:
            return self.client.storage.from_(self.settings.faces_bucket).download(f"{persona_id}/{name}")
        except StorageApiError as error:
            if str(getattr(error, "status", "")) in ("400", "404") or "not found" in str(error).lower():
                raise StorageNotFound(name) from error
            raise

    def upload(self, bucket: str, path: str, content: bytes, mime: str) -> None:
        self.client.storage.from_(bucket).upload(path, content, {"content-type": mime, "upsert": "false"})

    def upload_face(self, persona_id: str, name: str, content: bytes, mime: str) -> None:
        self.upload(self.settings.faces_bucket, f"{persona_id}/{name}", content, mime)

    def delete(self, table: str, key: str, value: Any) -> None:
        self.client.table(table).delete().eq(key, value).execute()

    def revoke_credentials(self, persona_id: str, when: str) -> None:
        self.client.table("credenciales").update({"revocada_en": when}).eq("persona_id", persona_id)             .is_("revocada_en", "null").execute()

    def signed_url(self, bucket: str, path: str, ttl: int) -> str | None:
        result = self.client.storage.from_(bucket).create_signed_url(path, ttl)
        return result.get("signedURL") or result.get("signedUrl")

    # ---------- Auth y Realtime ----------

    def auth_user_id(self, jwt: str) -> str | None:
        try:
            response = self.client.auth.get_user(jwt)
        except Exception:  # token caducado, revocado o mal formado
            return None
        return getattr(getattr(response, "user", None), "id", None)

    def broadcast(self, topic: str, event: str, payload: dict) -> None:
        """Broadcast a un canal privado; RLS en realtime.messages filtra a ADMIN."""
        try:
            self.http.post(
                f"{self.settings.supabase_url}/realtime/v1/api/broadcast",
                headers={
                    "apikey": self.settings.supabase_secret_key,
                    "Authorization": f"Bearer {self.settings.supabase_secret_key}",
                },
                json={"messages": [{"topic": topic, "event": event, "payload": payload, "private": True}]},
            ).raise_for_status()
        except httpx.HTTPError as error:
            log.warning("Realtime broadcast falló: %s", error)
