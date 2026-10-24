"""Contratos de entrada de la API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

RobotId = Field(pattern=r"^[A-Za-z0-9_-]{1,40}$")


class SolicitudAcceso(BaseModel):
    """Contrato original de nclub-backend/main.py, conservado."""

    face_group: Literal["member", "non_member", "unknown"]
    credential_code: str = Field(min_length=1, max_length=100)


class Heartbeat(BaseModel):
    name: str | None = Field(default=None, max_length=80)
    model: str | None = Field(default=None, max_length=80)
    firmware: str | None = Field(default=None, max_length=40)
    sdk_version: str | None = Field(default=None, max_length=40)
    camera_ok: bool = False
    mic_ok: bool = False
    mic_state: Literal["escuchando", "procesando", "silencio", "apagado", "desconocido"] = "desconocido"
    simulated: bool = False
    camera_topic: str | None = Field(default=None, max_length=200)
    audio_topic: str | None = Field(default=None, max_length=200)


class SessionStart(BaseModel):
    robot_id: str = RobotId
    simulated: bool = False


class FaceObservation(BaseModel):
    persona_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,60}$")
    similarity: float | None = Field(default=None, ge=-1, le=1)
    threshold: float | None = None
    second_persona_id: str | None = None
    second_similarity: float | None = None
    detection_score: float | None = None
    reason: str | None = Field(default=None, max_length=40)


class CredentialObservation(BaseModel):
    payload: str = Field(min_length=1, max_length=200)
    kind: Literal["secure", "static", "demo", "nfc", "manual"] = "static"


class Utterance(BaseModel):
    text: str = Field(default="", max_length=1000)
    language: str = Field(default="es-CO", max_length=10)
    confidence: float | None = None
    engine: str | None = Field(default=None, max_length=40)
    started_at: str | None = None
    ended_at: str | None = None
    # WAV 16 kHz mono en base64, solo con consentimiento y STORE_EVIDENCE=true.
    audio_wav_b64: str | None = Field(default=None, max_length=2_800_000)
    consent: bool = False


class ValidateRequest(BaseModel):
    credential_token: str = Field(min_length=1, max_length=200)
    method: Literal["qr", "nfc", "manual"] = "qr"
    simulation: bool = False


class CheckRequest(BaseModel):
    validation_id: str | None = Field(default=None, max_length=80)
    visitor_id: str | None = Field(default=None, max_length=60)
    scenario: str | None = Field(default=None, max_length=20)
    simulation: bool = False
    requested_outcome: Literal["authorized", "review", "denied"] | None = None


class EventRequest(BaseModel):
    event_type: Literal["assistance_requested"]


class RouteRequest(BaseModel):
    category: Literal["VIP", "REGULAR", "INVITADO", "PERSONAL_INTERNO", "TRABAJADOR_EXTERNO"]
    destination: str = Field(min_length=1, max_length=80)
    escort: bool = False


class TextRequest(BaseModel):
    text: str = Field(min_length=1, max_length=500)


class MemberRequest(BaseModel):
    nombre: str = Field(min_length=3, max_length=100)
    categoria: Literal["VIP", "REGULAR"]
    vigencia_hasta: str = Field(min_length=10, max_length=40)
    email: str | None = Field(default=None, max_length=120)
    telefono: str | None = Field(default=None, max_length=30)
    tipo_documento: Literal["CC", "CE", "PASAPORTE", "OTRO"]
    numero_documento: str = Field(min_length=5, max_length=30)
