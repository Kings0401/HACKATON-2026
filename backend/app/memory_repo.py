"""Repositorio en memoria con datos ficticios (equivalentes a supabase/datos_demo.sql).

Se usa en pruebas, en el simulador del robot y con NCLUB_BACKEND_MODE=memory.
Todas sus decisiones se marcan simulation=true: jamás autorizan un ingreso real.
"""

from __future__ import annotations

import copy
import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .repository import StorageNotFound


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def demo_tables(now: datetime | None = None) -> dict[str, list[dict]]:
    now = now or datetime.now(timezone.utc)
    start, end = _iso(now - timedelta(hours=1)), _iso(now + timedelta(hours=8))
    persona = lambda i, n, c, g, t, code: {  # noqa: E731
        "id": i, "nombre": n, "categoria": c, "grupo_facial": g, "tipo_credencial": t,
        "codigo_credencial": code, "activo": True, "auth_user_id": None, "email": None, "cargo": None,
    }
    return {
        "personas": [
            persona("VIP001", "Valeria Torres", "VIP", "member", "NFC", "NFC-VIP-001"),
            # El socio regular confirma su identidad con los últimos cuatro dígitos del documento.
            {**persona("REG001", "Santiago Ruiz", "REGULAR", "member", "APP", "APP-REG-001"),
             "tipo_documento": "CC", "numero_documento": "1020304567"},
            persona("INV001", "Camila López", "INVITADO", "non_member", "QR", "QR-INV-001"),
            persona("EMP001", "Daniel Moreno", "PERSONAL_INTERNO", "non_member", "CARNET", "CAR-EMP-001"),
            persona("EXT001", "Laura Pérez", "TRABAJADOR_EXTERNO", "non_member", "QR", "QR-EXT-001"),
            {**persona("ADMIN001", "Administración N Club", "ADMIN", "non_member", "CUENTA", "ADMIN-001"),
             "auth_user_id": "memory-admin"},
        ],
        "membresias": [
            {"persona_id": "VIP001", "nivel": "VIP", "estado": "ACTIVA", "vigencia_hasta": _iso(now + timedelta(days=180))},
            {"persona_id": "REG001", "nivel": "REGULAR", "estado": "ACTIVA", "vigencia_hasta": _iso(now + timedelta(days=180))},
        ],
        "reservas": [
            {"id": "RES001", "persona_id": "VIP001", "actividad": "Acceso a zona VIP", "destino": "VIP Lounge",
             "fecha_inicio": start, "fecha_fin": end, "estado": "CONFIRMADA", "servicio_id": "lounge"},
            {"id": "RES002", "persona_id": "REG001", "actividad": "Reserva de golf", "destino": "Campo de golf · Cancha 2",
             "fecha_inicio": start, "fecha_fin": end, "estado": "CONFIRMADA", "servicio_id": "golf-2"},
        ],
        "invitaciones": [
            {"codigo_qr": "QR-INV-001", "persona_id": "INV001", "anfitrion": "Valeria Torres", "anfitrion_id": "VIP001",
             "destino": "Restaurante principal", "valido_desde": start, "valido_hasta": end, "estado": "ACTIVA"},
        ],
        "permisos_laborales": [
            {"codigo_autorizacion": "CAR-EMP-001", "persona_id": "EMP001", "tipo": "PERSONAL_INTERNO",
             "actividad": "Turno administrativo", "destino": "Oficina administrativa", "valido_desde": start,
             "valido_hasta": end, "requiere_acompanamiento": False, "estado": "ACTIVO", "empresa": "N Club World"},
            {"codigo_autorizacion": "QR-EXT-001", "persona_id": "EXT001", "tipo": "TRABAJADOR_EXTERNO",
             "actividad": "Mantenimiento eléctrico", "destino": "Zona técnica", "valido_desde": start,
             "valido_hasta": end, "requiere_acompanamiento": True, "estado": "ACTIVO",
             "empresa": "Proveedor de mantenimiento"},
        ],
        "credenciales": [],
    }


KEYS = {
    "personas": "id", "membresias": "persona_id", "reservas": "id", "invitaciones": "codigo_qr",
    "permisos_laborales": "codigo_autorizacion", "robots": "id", "sesiones_atencion": "id",
    "rutas_compartidas": "token_hash",
}


class MemoryRepository:
    simulated = True

    def __init__(self, faces_dir: str | Path | None = None, tables: dict | None = None,
                 admin_token: str = "memory-admin-token"):
        self.tables: dict[str, list[dict]] = copy.deepcopy(tables) if tables else demo_tables()
        self.faces_dir = Path(faces_dir) if faces_dir else None
        self.files: dict[tuple[str, str], bytes] = {}
        self.uploaded_faces: dict[tuple[str, str], bytes] = {}
        self.uploaded_voices: dict[tuple[str, str], bytes] = {}
        self.broadcasts: list[tuple[str, str, dict]] = []
        self.admin_token = admin_token
        self.fail_tables: set[str] = set()  # para probar persistencia fallida

    def issue_token(self, persona_id: str, tipo: str, minutes: int = 60) -> str:
        """Equivalente a emitir_credencial: guarda solo el hash."""
        token = uuid.uuid4().hex + uuid.uuid4().hex
        self.tables["credenciales"].append({
            "id": str(uuid.uuid4()), "persona_id": persona_id,
            "token_hash": hashlib.sha256(token.encode()).hexdigest(), "tipo": tipo,
            "expira_en": _iso(datetime.now(timezone.utc) + timedelta(minutes=minutes)), "revocada_en": None,
        })
        return token

    def _rows(self, table: str) -> list[dict]:
        return self.tables.setdefault(table, [])

    def one(self, table: str, column: str, value: Any) -> dict | None:
        return next((copy.deepcopy(r) for r in self._rows(table) if r.get(column) == value), None)

    def persona(self, persona_id):
        return self.one("personas", "id", persona_id)

    def persona_by_document(self, document_type, document_number):
        return next((copy.deepcopy(r) for r in self._rows("personas")
                     if r.get("tipo_documento") == document_type and r.get("numero_documento") == document_number), None)

    def persona_by_code(self, code):
        return self.one("personas", "codigo_credencial", code)

    def persona_by_auth(self, auth_user_id):
        return self.one("personas", "auth_user_id", auth_user_id)

    def credential_by_hash(self, token_hash):
        return self.one("credenciales", "token_hash", token_hash)

    def membership(self, persona_id):
        return self.one("membresias", "persona_id", persona_id)

    def reservations(self, persona_id):
        return [copy.deepcopy(r) for r in self._rows("reservas")
                if r["persona_id"] == persona_id and r["estado"] == "CONFIRMADA"]

    def invitation_by_code(self, code):
        return self.one("invitaciones", "codigo_qr", code)

    def invitations(self, persona_id):
        return [copy.deepcopy(r) for r in self._rows("invitaciones") if r["persona_id"] == persona_id]

    def permit_by_code(self, code):
        return self.one("permisos_laborales", "codigo_autorizacion", code)

    def permits(self, persona_id):
        return [copy.deepcopy(r) for r in self._rows("permisos_laborales") if r["persona_id"] == persona_id]

    def insert(self, table, row):
        if table in self.fail_tables:
            raise RuntimeError(f"Fallo simulado al escribir {table}")
        row = {"created_at": _iso(datetime.now(timezone.utc)), **copy.deepcopy(row)}
        if table not in KEYS and "id" not in row:
            row["id"] = str(uuid.uuid4())
        self._rows(table).append(row)
        return copy.deepcopy(row)

    def update(self, table, key, value, values):
        if table in self.fail_tables:
            raise RuntimeError(f"Fallo simulado al escribir {table}")
        for row in self._rows(table):
            if row.get(key) == value:
                row.update(copy.deepcopy(values))

    def upsert(self, table, row):
        key = KEYS.get(table, "id")
        existing = next((r for r in self._rows(table) if r.get(key) == row.get(key)), None)
        if existing:
            existing.update(copy.deepcopy(row))
        else:
            self.insert(table, row)

    def recent(self, table, limit=20, **filters):
        rows = [r for r in self._rows(table) if all(r.get(k) == v for k, v in filters.items())]
        rows.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        return copy.deepcopy(rows[:limit])

    # ---------- Storage simulado ----------

    def face_folders(self):
        local = {p.name for p in self.faces_dir.iterdir() if p.is_dir()}             if self.faces_dir and self.faces_dir.is_dir() else set()
        return sorted(local | {pid for pid, _ in self.uploaded_faces})

    def face_files(self, persona_id):
        folder = (self.faces_dir or Path("/nonexistent")) / persona_id
        local = [p.name for p in folder.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png")]             if folder.is_dir() else []
        uploaded = [n for (pid, n) in self.uploaded_faces if pid == persona_id]
        return sorted(set(local) | set(uploaded))

    def download_face(self, persona_id, name):
        if (persona_id, name) in self.uploaded_faces:
            return self.uploaded_faces[(persona_id, name)]
        path = (self.faces_dir or Path("/nonexistent")) / persona_id / name
        if not path.is_file():
            raise StorageNotFound(name)
        return path.read_bytes()

    def voice_files(self, persona_id):
        return sorted(name for (pid, name) in self.uploaded_voices if pid == persona_id)

    def download_voice(self, persona_id, name):
        try:
            return self.uploaded_voices[(persona_id, name)]
        except KeyError as error:
            raise StorageNotFound(name) from error

    def upload_voice(self, persona_id, name, content, mime):
        self.uploaded_voices[(persona_id, name)] = bytes(content)

    def upload_face(self, persona_id, name, content, mime):
        # Solo en memoria: nunca escribe en vision/dataset.
        self.uploaded_faces[(persona_id, name)] = content

    def delete(self, table, key, value):
        self.tables[table] = [r for r in self._rows(table) if r.get(key) != value]

    def revoke_credentials(self, persona_id, when):
        for row in self._rows("credenciales"):
            if row["persona_id"] == persona_id and not row.get("revocada_en"):
                row["revocada_en"] = when

    def upload(self, bucket, path, content, mime):
        self.files[(bucket, path)] = content

    def signed_url(self, bucket, path, ttl):
        return f"memory://{bucket}/{path}?ttl={ttl}" if (bucket, path) in self.files else None

    def auth_user_id(self, jwt):
        return "memory-admin" if jwt == self.admin_token else None

    def broadcast(self, topic, event, payload):
        self.broadcasts.append((topic, event, payload))
