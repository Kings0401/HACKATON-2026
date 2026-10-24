"""Configuración del backend. Las claves privilegiadas solo viven en backend/.env."""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    return default if value is None else value.strip().lower() in ("1", "true", "yes", "si", "sí")


def _list(name: str, default: str) -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


@dataclass
class Settings:
    # supabase: datos reales. memory: datos ficticios en memoria, siempre simulation=true.
    mode: str = field(default_factory=lambda: os.getenv("NCLUB_BACKEND_MODE", "supabase"))
    supabase_url: str = field(default_factory=lambda: os.getenv("SUPABASE_URL", ""))
    supabase_secret_key: str = field(default_factory=lambda: os.getenv("SUPABASE_SECRET_KEY", ""))
    robot_api_key: str = field(default_factory=lambda: os.getenv("ROBOT_API_KEY", ""))
    cors_origins: list[str] = field(
        default_factory=lambda: _list(
            "CORS_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173"
        )
    )
    public_app_url: str = field(
        default_factory=lambda: os.getenv("PUBLIC_APP_URL", "http://127.0.0.1:5173").rstrip("/")
    )
    public_api_url: str = field(
        default_factory=lambda: os.getenv("PUBLIC_API_URL", "http://127.0.0.1:8000").rstrip("/")
    )
    club_map_path: Path = field(
        default_factory=lambda: Path(
            os.getenv("CLUB_MAP_PATH", BACKEND_DIR.parent / "shared" / "club-map.json")
        )
    )
    faces_bucket: str = field(default_factory=lambda: os.getenv("FACES_BUCKET", "rostros-nclub"))
    evidence_bucket: str = field(
        default_factory=lambda: os.getenv("EVIDENCE_BUCKET", "evidencias-recepcion")
    )
    # Guardar fotogramas/audio solo con política y consentimiento explícitos.
    store_evidence: bool = field(default_factory=lambda: _bool("STORE_EVIDENCE", False))
    evidence_retention_days: int = field(
        default_factory=lambda: int(os.getenv("EVIDENCE_RETENTION_DAYS", "30"))
    )
    # Umbral mínimo que FastAPI exige a la similitud informada por el agente.
    face_threshold: float = field(default_factory=lambda: float(os.getenv("FACE_THRESHOLD", "0.62")))
    face_required: list[str] = field(
        default_factory=lambda: _list("FACE_REQUIRED_CATEGORIES", "VIP,PERSONAL_INTERNO")
    )
    # Los códigos estáticos (NFC-VIP-001, QR-INV-001…) son de demostración.
    allow_static_credentials: bool = field(
        default_factory=lambda: _bool("ALLOW_STATIC_CREDENTIALS", True)
    )
    allow_simulation: bool = field(default_factory=lambda: _bool("ALLOW_SIMULATION", True))
    arrival_tolerance_min: int = field(
        default_factory=lambda: int(os.getenv("ARRIVAL_TOLERANCE_MIN", "60"))
    )
    session_timeout_s: int = field(default_factory=lambda: int(os.getenv("SESSION_TIMEOUT_S", "180")))
    stream_secret: str = field(
        default_factory=lambda: os.getenv("STREAM_SECRET") or secrets.token_hex(32)
    )
    stream_token_ttl_s: int = field(default_factory=lambda: int(os.getenv("STREAM_TOKEN_TTL_S", "120")))
    stream_max_s: int = field(default_factory=lambda: int(os.getenv("STREAM_MAX_S", "600")))
    route_share_ttl_min: int = field(
        default_factory=lambda: int(os.getenv("ROUTE_SHARE_TTL_MIN", "30"))
    )
    robot_offline_after_s: int = field(
        default_factory=lambda: int(os.getenv("ROBOT_OFFLINE_AFTER_S", "15"))
    )
    memory_admin_token: str = field(
        default_factory=lambda: os.getenv("MEMORY_ADMIN_TOKEN") or secrets.token_urlsafe(24)
    )

    def validate(self) -> None:
        if self.mode not in ("supabase", "memory"):
            raise RuntimeError("NCLUB_BACKEND_MODE debe ser supabase o memory")
        if not self.robot_api_key or len(self.robot_api_key) < 16:
            raise RuntimeError("ROBOT_API_KEY falta o es demasiado corta (mínimo 16 caracteres)")
        if self.mode == "supabase" and (not self.supabase_url or not self.supabase_secret_key):
            raise RuntimeError("Faltan SUPABASE_URL o SUPABASE_SECRET_KEY en backend/.env")


settings = Settings()
