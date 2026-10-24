"""Autenticación: robot (X-Robot-Key) y ADMIN (JWT de Supabase + personas)."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass
from typing import Any

from fastapi import Depends, Header, HTTPException, Request

from .config import Settings
from .repository import Repository
from .services.reception import MonitorState, ReceptionService


@dataclass
class Context:
    settings: Settings
    repo: Repository
    state: MonitorState
    reception: ReceptionService
    gallery: Any = None  # services.device_lab.FaceGallery (requiere OpenCV y modelos)
    lab: Any = None  # services.device_lab.DeviceLab
    lab_error: str | None = None


def ctx(request: Request) -> Context:
    return request.app.state.ctx


def verify_robot(x_robot_key: str | None = Header(default=None), c: Context = Depends(ctx)) -> None:
    if not x_robot_key or not secrets.compare_digest(x_robot_key, c.settings.robot_api_key):
        raise HTTPException(status_code=401, detail="Robot no autorizado")


def _bearer(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Inicie sesión para continuar.")
    return authorization.split(" ", 1)[1].strip()


def current_person(authorization: str | None = Header(default=None), c: Context = Depends(ctx)) -> dict:
    """Verifica el JWT con Supabase Auth y resuelve la persona por auth_user_id."""
    user_id = c.repo.auth_user_id(_bearer(authorization))
    if not user_id:
        raise HTTPException(status_code=401, detail="Sesión no válida o vencida.")
    persona = c.repo.persona_by_auth(user_id)
    if not persona or not persona["activo"]:
        raise HTTPException(status_code=403, detail="La cuenta no está vinculada a una persona activa.")
    return persona


def require_admin(persona: dict = Depends(current_person)) -> dict:
    if persona["categoria"] != "ADMIN":
        raise HTTPException(status_code=403, detail="Reservado al equipo administrativo.")
    return persona


# ---------- tokens cortos para el stream MJPEG (un <img> no envía JWT) ----------

def stream_token(settings: Settings, robot_id: str, admin_id: str) -> str:
    expires = int(time.time()) + settings.stream_token_ttl_s
    message = f"{robot_id}:{admin_id}:{expires}".encode()
    signature = hmac.new(settings.stream_secret.encode(), message, hashlib.sha256).hexdigest()
    return f"{admin_id}.{expires}.{signature}"


def verify_stream_token(settings: Settings, robot_id: str, token: str) -> bool:
    try:
        admin_id, expires, signature = token.rsplit(".", 2)
        if int(expires) < time.time():
            return False
    except ValueError:
        return False
    message = f"{robot_id}:{admin_id}:{expires}".encode()
    expected = hmac.new(settings.stream_secret.encode(), message, hashlib.sha256).hexdigest()
    return secrets.compare_digest(expected, signature)
