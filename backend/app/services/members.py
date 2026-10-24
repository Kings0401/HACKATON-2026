"""Alta de miembros desde ADMIN y emisión de credenciales temporales.

Equivale a lo que hacen en SQL emitir_credencial/crear_visitante, pero para
VIP/REGULAR: FastAPI usa la credencial de servidor y revalida cada campo.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from ..repository import Repository
from .access import parse_time


class MemberError(ValueError):
    pass


def create_member(repo: Repository, nombre: str, categoria: str, vigencia_hasta: str,
                  email: str | None = None) -> dict:
    nombre = " ".join(nombre.split())
    if not 3 <= len(nombre) <= 100:
        raise MemberError("Escriba un nombre válido (3 a 100 caracteres).")
    if categoria not in ("VIP", "REGULAR"):
        raise MemberError("La categoría debe ser VIP o REGULAR.")
    vence = parse_time(vigencia_hasta if "T" in vigencia_hasta else f"{vigencia_hasta}T23:59:59-05:00")
    now = datetime.now(timezone.utc)
    if not now < vence <= now + timedelta(days=3 * 366):
        raise MemberError("La vigencia debe ser futura y de máximo 3 años.")
    tipo = "NFC" if categoria == "VIP" else "APP"
    persona_id = f"MEM-{secrets.token_hex(4).upper()}"
    persona = {
        "id": persona_id,
        "nombre": nombre,
        "categoria": categoria,
        "grupo_facial": "member",
        "tipo_credencial": tipo,
        "codigo_credencial": f"{tipo}-{secrets.token_hex(6).upper()}",
        "activo": True,
        "email": (email or "").strip() or None,
    }
    repo.insert("personas", persona)
    try:
        repo.insert("membresias", {
            "persona_id": persona_id, "nivel": categoria, "estado": "ACTIVA",
            "vigencia_hasta": vence.isoformat(),
        })
    except Exception:
        # Compensación: no dejar una persona sin membresía recién creada.
        repo.delete("personas", "id", persona_id)
        raise
    return persona


def issue_credential(repo: Repository, persona: dict, minutes: int = 60) -> dict:
    """Token opaco de un solo titular; solo se guarda su SHA-256 (como emitir_credencial)."""
    if persona["categoria"] not in ("VIP", "REGULAR"):
        raise MemberError("Esta operación emite credenciales de miembros.")
    membership = repo.membership(persona["id"])
    now = datetime.now(timezone.utc)
    if not persona["activo"] or not membership or membership["estado"] != "ACTIVA" \
            or parse_time(membership["vigencia_hasta"]) <= now:
        raise MemberError("La membresía no está vigente.")
    expires = min(now + timedelta(minutes=minutes), parse_time(membership["vigencia_hasta"]))
    token = secrets.token_hex(32)
    repo.revoke_credentials(persona["id"], now.isoformat())
    repo.insert("credenciales", {
        "persona_id": persona["id"],
        "token_hash": hashlib.sha256(token.encode()).hexdigest(),
        "tipo": "MIEMBRO",
        "expira_en": expires.isoformat(),
    })
    return {"token": token, "expires_at": expires.isoformat()}
