"""Motor de decisión de acceso. Reutiliza las reglas de nclub-backend/main.py
(/resolve-access) y añade credenciales seguras, rostro + credencial, anfitrión
y registro de cada comprobación.

Principios: ante cualquier duda se responde REVISIÓN. Cada categoría tiene su
propio segundo factor junto al rostro:

- VIP: rostro + voz registrada (sin credencial).
- REGULAR: rostro + nombre completo + últimos cuatro dígitos del documento + voz registrada.
- INVITADO: rostro + QR de invitación con anfitrión vigente.
- PERSONAL_INTERNO: rostro + carné/QR cruzado con el horario del turno.
- TRABAJADOR_EXTERNO: rostro + QR de la orden de trabajo.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from ..config import Settings
from ..repository import Repository

ROLE = {
    "VIP": "VIP",
    "REGULAR": "REGULAR",
    "INVITADO": "GUEST",
    "PERSONAL_INTERNO": "STAFF",
    "TRABAJADOR_EXTERNO": "EXTERNAL",
    "ADMIN": "ADMIN",
}
CATEGORY = {v: k for k, v in ROLE.items()}
ESTADO = {
    "authorized": "AUTORIZADO",
    "denied": "DENEGADO",
    "review": "REVISION",
    "pending_escort": "PENDIENTE",
    "pending": "PENDIENTE",
}
DECISION = {
    "authorized": "AUTORIZADO",
    "denied": "DENEGADO",
    "review": "REVISION",
    "pending_escort": "ACOMPANAMIENTO",
}
TOKEN = re.compile(r"^[0-9a-f]{64}$")
SECURE_PREFIX = "nclub:v1:"
CREDENTIAL_METHOD = {"NFC": "credencial NFC", "APP": "aplicación", "QR": "QR", "CARNET": "carné"}


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@dataclass
class FaceEvidence:
    persona_id: str | None
    similarity: float | None = None
    reason: str = ""
    voice_identity: str | None = None
    voice_similarity: float | None = None
    voice_checked: bool = False
    document_identity: str | None = None  # persona que verificó nombre, documento y voz (regular)
    identity_voice_similarity: float | None = None


# Socios que se identifican sin credencial: rostro + su factor propio.
FACE_FIRST = ("VIP", "REGULAR")


@dataclass
class Check:
    name: str
    ok: bool
    detail: str

    def as_dict(self) -> dict:
        return {"name": self.name, "ok": self.ok, "detail": self.detail}


@dataclass
class Decision:
    access: str  # authorized | denied | review | pending_escort
    reason: str
    instruction: str
    persona: dict | None = None
    destination: str | None = None
    robot_target: str = "robot1"
    event_type: str = "access_check"
    methods: list[str] = field(default_factory=list)
    checks: list[Check] = field(default_factory=list)
    escort: bool = False
    reservation_label: str | None = None
    simulation: bool = False

    @property
    def category(self) -> str | None:
        return self.persona["categoria"] if self.persona else None

    @property
    def role(self) -> str | None:
        return ROLE.get(self.category or "")

    def to_api(self) -> dict:
        return {
            "visitor_id": self.persona["id"] if self.persona else None,
            "visitor_name": self.persona["nombre"] if self.persona else None,
            "role": self.role,
            "category": self.category,
            "access": "pending" if self.access == "pending_escort" else self.access,
            "decision": DECISION[self.access],
            "escort_required": self.escort,
            "destination": self.destination,
            "robot_target": self.robot_target,
            "event_type": self.event_type,
            "simulation": self.simulation,
            "reason": self.reason,
            "instruction": self.instruction,
            "methods": self.methods,
            "checks": [c.as_dict() for c in self.checks],
            "reservation_label": self.reservation_label,
        }


class AccessEngine:
    def __init__(self, repo: Repository, settings: Settings):
        self.repo = repo
        self.settings = settings

    # ---------- credenciales ----------

    def resolve_credential(self, raw: str, checks: list[Check], methods: list[str]) -> tuple[dict | None, str | None]:
        """Devuelve (persona, código estático usado o None)."""
        code = (raw or "").strip()
        if not code:
            checks.append(Check("credencial", False, "No se presentó credencial"))
            return None, None
        if code.lower().startswith("demo_"):
            checks.append(Check("credencial", False, "Credencial DEMO: jamás válida en el canal real"))
            return None, None
        token = code[len(SECURE_PREFIX):] if code.startswith(SECURE_PREFIX) else code
        if TOKEN.fullmatch(token):
            methods.append("QR seguro")
            row = self.repo.credential_by_hash(hashlib.sha256(token.encode()).hexdigest())
            now = datetime.now(timezone.utc)
            if not row:
                checks.append(Check("credencial", False, "Token no emitido por N Club"))
                return None, None
            if row.get("revocada_en") or parse_time(row["expira_en"]) <= now:
                checks.append(Check("credencial", False, "Token revocado o vencido"))
                return None, None
            checks.append(Check("credencial", True, f"Token {row['tipo']} vigente"))
            return self.repo.persona(row["persona_id"]), None
        if not self.settings.allow_static_credentials:
            checks.append(Check("credencial", False, "Códigos estáticos deshabilitados"))
            return None, None
        persona = self.repo.persona_by_code(code)
        if not persona:
            checks.append(Check("credencial", False, "Credencial no encontrada"))
            return None, None
        methods.append(CREDENTIAL_METHOD.get(persona["tipo_credencial"], "credencial") + " (código de demostración)")
        checks.append(Check("credencial", True, f"Código {persona['tipo_credencial']} registrado"))
        return persona, code

    # ---------- rostro ----------

    def check_face(self, persona: dict, face: FaceEvidence | None, face_group: str | None,
                   checks: list[Check], methods: list[str]) -> str | None:
        """Devuelve None si el rostro es aceptable o un motivo de revisión."""
        required = persona["categoria"] in self.settings.face_required or persona["categoria"] in FACE_FIRST
        if face_group is not None:  # contrato original /resolve-access
            methods.append("grupo facial")
            if face_group == "unknown":
                checks.append(Check("rostro", False, "Sin resultado facial confiable"))
                return "No fue posible obtener un resultado facial confiable."
            if face_group != persona["grupo_facial"]:
                checks.append(Check("rostro", False, "El grupo facial no coincide con la credencial"))
                return "La identificación facial no coincide con la credencial."
            checks.append(Check("rostro", True, f"Grupo facial {face_group} coincide"))
            if persona["categoria"] == "VIP":
                checks.append(Check("voz", False, "El contrato heredado no incluye audio para verificar al locutor"))
                return "Recepción debe verificar la voz antes de autorizar el acceso."
            if persona["categoria"] == "REGULAR":
                checks.append(Check("pregunta de identidad", False, "El contrato heredado no incluye la pregunta"))
                return "Recepción debe confirmar la identidad del socio."
            return None
        if face is None or face.persona_id is None:
            detail = "Rostro no reconocido" if face else "Sin observación facial"
            checks.append(Check("rostro", not required, detail + ("" if required else " (opcional para la categoría)")))
            return "Se requiere confirmar la identidad facial en recepción." if required else None
        methods.append("facial")
        if face.persona_id != persona["id"]:
            checks.append(Check("rostro", False, "El rostro corresponde a otra persona registrada"))
            return "La identificación facial no coincide con la credencial."
        if face.similarity is None or face.similarity < self.settings.face_threshold:
            checks.append(Check("rostro", False, f"Similitud {face.similarity} bajo el umbral {self.settings.face_threshold}"))
            return "La similitud facial es insuficiente."
        checks.append(Check("rostro", True, f"Coincide con el registro (similitud {face.similarity:.2f})"))
        if persona["categoria"] == "VIP":
            if not face.voice_checked or face.voice_identity != persona["id"]:
                checks.append(Check("voz", False, "La voz no coincide o todavía no se verificó"))
                return "Confirme su identidad hablando con recepción; la voz registrada no coincidió."
            checks.append(Check("voz", True, f"Coincide con la voz registrada (similitud {face.voice_similarity:.2f})"))
        if persona["categoria"] == "REGULAR":
            if face.document_identity != persona["id"]:
                checks.append(Check("pregunta de identidad", False, "Nombre, documento o voz sin confirmar"))
                return "Confirme su identidad en recepción con su documento."
            checks.append(Check("pregunta de identidad", True, "Nombre completo y últimos cuatro dígitos del documento"))
            similarity = face.identity_voice_similarity
            checks.append(Check("voz", True, "Coincide con la voz registrada"
                                + (f" (similitud {similarity:.2f})" if similarity is not None else "")))
        return None

    # ---------- reglas por categoría ----------

    def _in_window(self, row: dict, start: str, end: str, tolerance: int = 0) -> bool:
        now = datetime.now(timezone.utc)
        return parse_time(row[start]) - timedelta(minutes=tolerance) <= now <= parse_time(row[end])

    def _membership_ok(self, persona: dict, checks: list[Check]) -> bool:
        m = self.repo.membership(persona["id"])
        ok = bool(
            m
            and m["nivel"] == persona["categoria"]
            and m["estado"] == "ACTIVA"
            and parse_time(m["vigencia_hasta"]) >= datetime.now(timezone.utc)
        )
        checks.append(Check("membresía", ok, "Activa y vigente" if ok else "Inactiva, vencida o no coincide"))
        return ok

    def evaluate(self, credential: str | None = None, face: FaceEvidence | None = None,
                 face_group: str | None = None, persona_id: str | None = None,
                 simulation: bool = False) -> Decision:
        checks: list[Check] = []
        methods: list[str] = []
        simulation = simulation or self.repo.simulated
        static_code = None
        if persona_id is not None:  # banco de pruebas ADMIN: credencial supuesta
            persona = self.repo.persona(persona_id)
            methods.append("simulación ADMIN")
            checks.append(Check("credencial", persona is not None, "Credencial supuesta en simulación"))
            static_code = persona.get("codigo_credencial") if persona else None
        elif not (credential or "").strip() and self._face_first(face):
            # VIP y regular: el rostro propone la identidad y su factor propio la confirma.
            persona = self.repo.persona(face.persona_id)
        else:
            persona, static_code = self.resolve_credential(credential or "", checks, methods)

        def done(access: str, reason: str, instruction: str, **kw) -> Decision:
            return Decision(access, reason, instruction, persona=persona, methods=methods,
                            checks=checks, simulation=simulation, **kw)

        if not persona:
            # Sin identidad confirmada nunca se autoriza; un rostro conocido sin
            # credencial pasa a recepción para atención personalizada.
            if face and face.persona_id:
                return done("review", "Rostro reconocido sin credencial válida",
                            "Por favor, muestre su credencial o acérquese a recepción.",
                            destination="Recepción")
            return done("denied", "Credencial no válida", "Credencial no encontrada. Acérquese a recepción.")
        category = persona["categoria"]
        first = persona["nombre"].split()[0]
        if not persona["activo"]:
            checks.append(Check("persona activa", False, "Registro inactivo"))
            return done("denied", "Persona inactiva", "El usuario se encuentra inactivo.")
        checks.append(Check("persona activa", True, "Registro activo"))
        if category == "ADMIN":
            return done("denied", "Cuenta administrativa", "La cuenta administrativa no es una credencial de visitante.")
        face_issue = self.check_face(persona, face, face_group, checks, methods)
        if face_issue:
            return done("review", face_issue, "Un miembro de recepción le atenderá en un momento.",
                        destination="Recepción")

        if category in ("VIP", "REGULAR"):
            if not self._membership_ok(persona, checks):
                return done("denied", "Membresía no válida", "Membresía inactiva, vencida o no válida.")
            current = next(
                (r for r in self.repo.reservations(persona["id"])
                 if self._in_window(r, "fecha_inicio", "fecha_fin", self.settings.arrival_tolerance_min)),
                None,
            )
            checks.append(Check("reserva", True, f"{current['actividad']} · {current['destino']}" if current
                                else "Sin reserva en la ventana de llegada"))
            label = f"{current['actividad']} · {parse_time(current['fecha_inicio']).astimezone(timezone(timedelta(hours=-5))).strftime('%H:%M')}" if current else None
            if category == "VIP":
                return done("authorized", "Membresía VIP, rostro y voz verificados",
                            f"Gracias, {first}. Reconocí su rostro y su voz; es un placer atenderle. "
                            "Disfrute de su experiencia VIP.",
                            destination=current["destino"] if current else "Recepción VIP",
                            robot_target="robot2", event_type="vip_handoff", reservation_label=label)
            return done("authorized", "Membresía, rostro e identidad verificados",
                        f"Acceso aprobado, {first}. Su membresía regular está vigente. "
                        "Le indicaré cómo llegar a su actividad.",
                        destination=current["destino"] if current else "Recepción de miembros",
                        reservation_label=label)

        if category == "INVITADO":
            invitation = (self.repo.invitation_by_code(static_code) if static_code else None) or next(
                (i for i in self.repo.invitations(persona["id"])
                 if i["estado"] == "ACTIVA" and self._in_window(i, "valido_desde", "valido_hasta")),
                None,
            )
            valid = bool(
                invitation
                and invitation["persona_id"] == persona["id"]
                and invitation["estado"] == "ACTIVA"
                and self._in_window(invitation, "valido_desde", "valido_hasta")
            )
            checks.append(Check("invitación", valid, "Vigente" if valid else "No vigente o inexistente"))
            if not valid:
                return done("denied", "Invitación no vigente", "La invitación no está vigente.")
            host = self.repo.persona(invitation["anfitrion_id"]) if invitation.get("anfitrion_id") else None
            host_ok = bool(host and host["activo"] and self._host_member(host))
            checks.append(Check("anfitrión", host_ok, f"{invitation['anfitrion']} con membresía vigente"
                                if host_ok else "Anfitrión sin identificar o sin membresía vigente"))
            if not host_ok:
                return done("review", "Anfitrión sin verificar", "Recepción confirmará su invitación con el anfitrión.",
                            destination="Recepción")
            checks.append(Check("destino", True, invitation["destino"]))
            return done("authorized", "Invitación y anfitrión verificados",
                        f"Invitación confirmada, {first}. Su anfitrión es {invitation['anfitrion']}.",
                        destination=invitation["destino"])

        if category in ("PERSONAL_INTERNO", "TRABAJADOR_EXTERNO"):
            permit = (self.repo.permit_by_code(static_code) if static_code else None) or next(
                (p for p in self.repo.permits(persona["id"])
                 if p["estado"] == "ACTIVO" and self._in_window(p, "valido_desde", "valido_hasta")),
                None,
            )
            valid = bool(
                permit
                and permit["persona_id"] == persona["id"]
                and permit["tipo"] == category
                and permit["estado"] == "ACTIVO"
                and self._in_window(permit, "valido_desde", "valido_hasta")
            )
            if category == "PERSONAL_INTERNO":
                checks.append(Check("horario de trabajo", valid, f"{permit['actividad']} · {self._shift(permit)}"
                                    if valid else "Fuera de su horario de trabajo o sin turno asignado"))
                if not valid:
                    return done("denied", "Fuera del horario de trabajo", "No tiene un turno asignado en este horario.")
            else:
                checks.append(Check("orden de trabajo", valid, f"{permit['actividad']} · {permit['destino']}"
                                    if valid else "Sin orden de trabajo vigente"))
                if not valid:
                    return done("denied", "Sin orden de trabajo vigente", "No existe una orden de trabajo vigente.")
            if permit["requiere_acompanamiento"]:
                checks.append(Check("acompañamiento", True, "Requerido: espere en Recepción de proveedores"))
                return done("pending_escort", "Orden vigente; requiere acompañamiento",
                            f"Gracias. Su orden de servicio para {permit['actividad']} está vigente. "
                            "Espere a su acompañante.",
                            destination=permit["destino"], escort=True)
            return done("authorized", "Permiso laboral verificado",
                        f"Listo, {first}. Su carné es válido y su turno está activo hasta las "
                        f"{self._local_time(permit['valido_hasta'])}. "
                        "Puede dirigirse a su área de trabajo.",
                        destination=permit["destino"])

        return done("denied", "Categoría no admitida", "Categoría no admitida.")

    def _face_first(self, face: FaceEvidence | None) -> bool:
        if not face or not face.persona_id or face.persona_id == "__conflict__":
            return False
        if face.similarity is None or face.similarity < self.settings.face_threshold:
            return False
        persona = self.repo.persona(face.persona_id)
        return bool(persona and persona["categoria"] in FACE_FIRST)

    @staticmethod
    def _local_time(value: str) -> str:
        return parse_time(value).astimezone(timezone(timedelta(hours=-5))).strftime("%H:%M")

    def _shift(self, permit: dict) -> str:
        return f"turno {self._local_time(permit['valido_desde'])}–{self._local_time(permit['valido_hasta'])}, dentro del horario"

    def _host_member(self, host: dict) -> bool:
        m = self.repo.membership(host["id"])
        return bool(
            host["categoria"] in ("VIP", "REGULAR")
            and m
            and m["nivel"] == host["categoria"]
            and m["estado"] == "ACTIVA"
            and parse_time(m["vigencia_hasta"]) > datetime.now(timezone.utc)
        )
