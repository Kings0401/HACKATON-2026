"""Sesiones de atención del robot: observaciones, voz, decisión, ruta y auditoría.

Registra en PostgreSQL (tablas de supabase/recepcion_robot.sql). Si esas
tablas aún no existen, la recepción sigue funcionando con estado en memoria y
el monitor indica persistencia degradada. eventos_acceso es obligatorio: sin
poder registrar la decisión no se comunica un acceso autorizado.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import re
import secrets
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timedelta, timezone

from ..config import Settings
from ..repository import Repository
from . import club_guide, dialogue
from .access import ESTADO, DECISION, AccessEngine, Decision, FaceEvidence
from .navigation import RouteError, compute_route

log = logging.getLogger(__name__)
MONITOR_TOPIC = "nclub:monitor"
# Cierre hablado de cada uno de los cinco flujos.
CATEGORY_CLOSING = {
    ("VIP", "authorized"): "Mi compañero AGIBOT 02 ya viene por usted para darle una atención preferencial.",
    ("REGULAR", "authorized"): "Que disfrute su visita en N Club.",
    ("INVITADO", "authorized"): "Su anfitrión ya fue notificado; la ruta solo incluye las áreas de su invitación.",
    ("PERSONAL_INTERNO", "authorized"): "Que tenga una excelente jornada, y recuerde llevar su carné visible.",
    ("TRABAJADOR_EXTERNO", "pending_escort"): "Por seguridad, permanezca en la recepción de proveedores hasta que llegue su acompañante y no ingrese a áreas sociales.",
}


# Primer saludo al reconocer el rostro: cada categoría tiene su propio trato y su paso de diálogo.
GREETINGS = {
    # VIP: trato preferencial; su voz al responder es el segundo factor.
    "VIP": ("activity", "{salutation}, {first}. ¡Qué gusto tenerle de nuevo en N Club! Con su membresía VIP "
                        "tiene atención preferencial. Cuénteme, ¿qué le gustaría disfrutar hoy?"),
    # Regular: verificación estricta de nombre, documento y voz antes de continuar.
    "REGULAR": ("identity", "{salutation}, {first}. Le damos la bienvenida a N Club. Antes de continuar debo "
                            "verificar su identidad: dígame su nombre completo y los últimos cuatro dígitos "
                            "de su documento, por favor."),
    # Invitado: bienvenida directa y pide el QR de invitación apenas lo detecta.
    "INVITADO": ("guest_qr", "¡{first}, bienvenidos a N Club! Por favor, muéstrame tu código QR de invitación."),
    # Personal interno: conversación cercana antes de pedir el carné.
    "PERSONAL_INTERNO": ("staff_card", "¡Hola, {first}! Qué gusto verle por aquí. ¿Cómo va su día? "
                                       "Cuando quiera, acerque su carné a mi cámara y verifico su turno."),
    "TRABAJADOR_EXTERNO": ("work_order", "{salutation}, {first}. Le damos la bienvenida al área de proveedores de N Club. "
                                         "Para registrar su ingreso, muestre a mi cámara el código QR de su "
                                         "orden de servicio, por favor."),
}
# Respuesta mientras se espera el QR de cada categoría.
QR_PROMPTS = {
    "guest_qr": "Por favor, muéstrame tu código QR de invitación para confirmar a tu anfitrión.",
    "staff_card": "¡Me alegra! Ahora acerque su carné a mi cámara, por favor, y reviso que su turno esté activo.",
    "work_order": "Gracias. Muestre a mi cámara el código QR de su orden de servicio, por favor.",
}
REGULAR_PARTS = {"name": "su nombre completo", "document": "los últimos cuatro dígitos de su documento"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def mask_credential(raw: str) -> str:
    """Nunca se registra el token o código completo."""
    raw = raw.strip()
    if raw.startswith("nclub:v1:"):
        return "nclub:v1:…" + raw[-4:]
    return raw[:4] + "…" if len(raw) > 4 else "…"


class MonitorState:
    """Estado en vivo (no persistente): latidos, último fotograma y voz."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.robots: dict[str, dict] = {}
        self.frames: dict[str, tuple[bytes, float]] = {}
        self.sessions: dict[str, dict] = {}
        self.history: deque[dict] = deque(maxlen=50)
        self.transcripts: deque[dict] = deque(maxlen=50)
        self.shared_routes: dict[str, dict] = {}
        self.validations: dict[str, dict] = {}
        self.degraded: dict[str, str] = {}
        self.gallery_cache: tuple[float, dict] | None = None


class ReceptionService:
    def __init__(self, repo: Repository, settings: Settings, state: MonitorState):
        self.repo = repo
        self.settings = settings
        self.state = state
        self.engine = AccessEngine(repo, settings)

    # ---------- persistencia tolerante ----------

    def _safe(self, table: str, action, *args) -> bool:
        try:
            action(table, *args)
            self.state.degraded.pop(table, None)
            return True
        except Exception as error:  # tabla ausente, red, RLS…
            self.state.degraded[table] = type(error).__name__
            log.warning("No se pudo escribir %s: %s", table, error)
            return False

    def audit(self, actor: str, action: str, entity: str, entity_id: str, detail: dict | None = None) -> None:
        self._safe("auditoria", self.repo.insert, {
            "actor": actor, "accion": action, "entidad": entity, "entidad_id": entity_id, "detalle": detail or {},
        })

    def _publish(self, event: str, payload: dict) -> None:
        self.repo.broadcast(MONITOR_TOPIC, event, payload)

    # ---------- galería facial (sincronización en vivo) ----------

    def gallery_manifest(self, max_age_s: float = 4.0) -> dict:
        """Listado de fotos por persona y una versión que cambia con cada alta o baja."""
        cached = self.state.gallery_cache
        if cached and time.time() - cached[0] < max_age_s:
            return cached[1]
        personas = {pid: self.repo.face_files(pid) for pid in self.repo.face_folders()}
        personas = {pid: files for pid, files in personas.items() if files}
        version = hashlib.sha1(repr(sorted(personas.items())).encode()).hexdigest()[:16]
        manifest = {"version": version, "personas": personas, "generated_at": now_iso()}
        self.state.gallery_cache = (time.time(), manifest)
        return manifest

    def invalidate_gallery(self) -> None:
        self.state.gallery_cache = None
        self._publish("gallery", {"changed": True})

    def public_status(self) -> dict:
        """Estado mínimo para mostrar la conexión sin sesión (sin cámara ni datos)."""
        robots = [self.robot_status(r) for r in sorted(self.state.robots)]
        return {
            "updated_at": now_iso(),
            "robots": [{k: r.get(k) for k in ("robot_id", "name", "connected", "camera_ok", "mic_ok",
                                               "mic_state", "simulated", "seconds_since_heartbeat")}
                       for r in robots],
        }

    # ---------- robots ----------

    def heartbeat(self, robot_id: str, payload: dict) -> dict:
        info = {**payload, "robot_id": robot_id, "last_seen": time.time()}
        with self.state.lock:
            previous = self.state.robots.get(robot_id)
            self.state.robots[robot_id] = info
        row = {
            "id": robot_id,
            "nombre": payload.get("name") or robot_id,
            "modelo": payload.get("model"),
            "firmware": payload.get("firmware"),
            "sdk_version": payload.get("sdk_version"),
            "estado": "CONECTADO" if payload.get("camera_ok") and payload.get("mic_ok") else "DEGRADADO",
            "camara_ok": bool(payload.get("camera_ok")),
            "microfono_ok": bool(payload.get("mic_ok")),
            "simulado": bool(payload.get("simulated")),
            "ultimo_latido": now_iso(),
        }
        # Solo se persiste el cambio de estado para no escribir cada latido.
        if not previous or any(previous.get(k) != payload.get(k) for k in ("camera_ok", "mic_ok", "firmware")) \
                or time.time() - previous.get("persisted_at", 0) > 60:
            if self._safe("robots", self.repo.upsert, row):
                info["persisted_at"] = time.time()
            self._publish("robot", {"robot_id": robot_id, "estado": row["estado"],
                                    "camara_ok": row["camara_ok"], "microfono_ok": row["microfono_ok"]})
        return {"ok": True, "server_time": now_iso()}

    def robot_status(self, robot_id: str) -> dict:
        # Un robot puede enviar fotogramas antes de su primer latido.
        info = self.state.robots.get(robot_id) or {"last_seen": 0.0}
        age = time.time() - info["last_seen"]
        return {
            "robot_id": robot_id,
            "connected": age < self.settings.robot_offline_after_s,
            "seconds_since_heartbeat": round(age, 1) if info["last_seen"] else None,
            "camera_ok": bool(info.get("camera_ok")),
            "mic_ok": bool(info.get("mic_ok")),
            "mic_state": info.get("mic_state", "desconocido"),
            "name": info.get("name") or robot_id,
            "model": info.get("model"),
            "firmware": info.get("firmware"),
            "sdk_version": info.get("sdk_version"),
            "simulated": bool(info.get("simulated")),
        }

    # ---------- sesiones ----------

    def start(self, robot_id: str, simulated: bool = False) -> dict:
        session = {
            "id": str(uuid.uuid4()),
            "robot_id": robot_id,
            "started_at": now_iso(),
            "status": "ACTIVA",
            "faces": [],
            "credential": None,
            "credential_masked": None,
            "credential_kind": None,
            "category_hint": None,
            "transcripts": [],
            "decision": None,
            "simulation": simulated or self.repo.simulated,
            "last_activity": time.time(),
            "dialogue_step": None,
            "voice_identity": None,
            "document_identity": None,
            "identity_attempts": 0,
            "requested_activity": None,
        }
        with self.state.lock:
            self.state.sessions[session["id"]] = session
        self._safe("sesiones_atencion", self.repo.insert, {
            "id": session["id"], "robot_id": robot_id, "estado": "ACTIVA",
            "iniciada_en": session["started_at"], "simulacion": session["simulation"],
        })
        self._publish("session", {"id": session["id"], "robot_id": robot_id, "estado": "ACTIVA"})
        return self.public(session)

    def get(self, session_id: str) -> dict | None:
        session = self.state.sessions.get(session_id)
        if session and session["status"] == "ACTIVA" and time.time() - session["last_activity"] > self.settings.session_timeout_s:
            self.close(session_id, "EXPIRADA")
        return session

    def _identification(self, session: dict, tipo: str, resultado: str, detalle: dict,
                        persona: str | None = None, similitud: float | None = None) -> None:
        session["last_activity"] = time.time()
        self._safe("eventos_identificacion", self.repo.insert, {
            "sesion_id": session["id"], "tipo": tipo, "resultado": resultado, "persona_candidata": persona,
            "similitud": similitud, "umbral": self.settings.face_threshold if tipo == "ROSTRO" else None,
            "detalle": detalle,
        })
        self._publish("identification", {"sesion_id": session["id"], "tipo": tipo, "resultado": resultado,
                                         "persona_candidata": persona})

    def add_face(self, session: dict, obs: dict) -> dict:
        persona = obs.get("persona_id")
        similarity = obs.get("similarity")
        ok = bool(persona and similarity is not None and similarity >= self.settings.face_threshold)
        session["faces"].append({**obs, "accepted": ok})
        candidate = self.repo.persona(persona) if ok else None
        if candidate and not session["category_hint"]:
            session["category_hint"] = candidate["categoria"]
        self._identification(session, "ROSTRO", "COINCIDE" if ok else "DESCONOCIDO",
                             {k: obs.get(k) for k in ("reason", "second_persona_id", "second_similarity", "detection_score")},
                             persona if ok else None, similarity)
        greeting = None
        # El robot reporta el rostro cada pocos segundos: se saluda y se fija el paso solo una vez.
        if candidate and candidate["activo"] and session.get("dialogue_step") is None:
            first = candidate["nombre"].split()[0]
            hour = datetime.now(timezone(timedelta(hours=-5))).hour
            salutation = "Buenos días" if hour < 12 else "Buenas tardes" if hour < 19 else "Buenas noches"
            step, greeting = GREETINGS.get(candidate["categoria"], (None, None))
            if step:
                session["dialogue_step"] = step
                greeting = greeting.format(salutation=salutation, first=first)
        return {"accepted": ok, "category_hint": session["category_hint"], "speech": greeting}

    def add_credential(self, session: dict, payload: str, kind: str) -> dict:
        session["credential"] = payload
        session["credential_masked"] = mask_credential(payload)
        session["credential_kind"] = kind
        self._identification(session, "QR" if kind in ("qr", "secure", "static", "demo") else "CREDENCIAL",
                             "LEIDO", {"credencial": session["credential_masked"], "formato": kind})
        return {"received": True}

    def add_utterance(self, session: dict, text: str, language: str = "es-CO", confidence: float | None = None,
                      engine: str | None = None, started_at: str | None = None, ended_at: str | None = None,
                      audio_b64: str | None = None, consent: bool = False,
                      speaker_audio_b64: str | None = None) -> dict:
        text = text.strip()[:1000]
        speaker_match = None
        ready = False  # identificación completa: el robot puede pedir la decisión
        face = self.best_face(session)
        if face and face.persona_id not in (None, "__conflict__"):
            session["voice_identity"] = None
            session["voice_similarity"] = None
            session["voice_checked"] = False
        if speaker_audio_b64 and face and face.persona_id not in (None, "__conflict__"):
            try:
                audio = base64.b64decode(speaker_audio_b64, validate=True)
                files = self.repo.voice_files(face.persona_id)
                phrase_files = [name for name in files if name.startswith("frase-") and name.endswith(".wav")]
                phrase_ids = {name[6:-4] for name in phrase_files if name[6:-4].isdigit()}
                if phrase_files:
                    references = phrase_files if {"1", "2", "3"}.issubset(phrase_ids) else []
                else:
                    references = ["enrollment.wav"] if "enrollment.wav" in files else files[:1]
                if references:
                    from .speaker_id import verify_many

                    speaker_match = verify_many(
                        [self.repo.download_voice(face.persona_id, name) for name in references], audio,
                        self.settings.speaker_threshold,
                    )
                    session["voice_identity"] = face.persona_id if speaker_match["matched"] else None
                    session["voice_similarity"] = speaker_match["similarity"]
                    session["voice_checked"] = True
                    self._identification(session, "VOZ", "COINCIDE" if speaker_match["matched"] else "NO_COINCIDE",
                                         {"modelo": speaker_match["model"], "umbral": speaker_match["threshold"],
                                          "coincidencias": speaker_match["matches"],
                                          "muestras": speaker_match["samples"]}, face.persona_id,
                                         speaker_match["similarity"])
            except Exception as error:
                log.warning("No se pudo verificar la voz en esta intervención: %s", error)
        step = session.get("dialogue_step")
        if step == "identity" and face and face.persona_id:
            understanding = self._regular_identity(session, face.persona_id, text)
            ready = understanding.pop("ready", False)
        elif step == "activity" and text:
            session["requested_activity"] = text[:160]
            persona = self.repo.persona(face.persona_id) if face and face.persona_id else None
            voice_ok = bool(face and session.get("voice_identity") == face.persona_id)
            if persona and persona["categoria"] == "VIP" and not voice_ok and self._retry(session):
                reply = ("Disculpe, no alcancé a reconocer su voz. ¿Sería tan amable de repetirme "
                         "qué le gustaría disfrutar hoy?")
                understanding = {"intent": "VOZ_PENDIENTE", "category_hint": "VIP", "reply": reply, "handoff": False}
            else:
                # VIP (rostro + voz) y regular (rostro + nombre, documento y voz) no necesitan credencial.
                session["dialogue_step"] = "done"
                ready = True
                understanding = {"intent": "ACTIVIDAD_SOLICITADA", "category_hint": session.get("category_hint"),
                                 "reply": None, "handoff": False}
        elif step in QR_PROMPTS and text and not session.get("decision"):
            understanding = {"intent": "ESPERANDO_CREDENCIAL", "category_hint": session.get("category_hint"),
                             "reply": QR_PROMPTS[step], "handoff": False}
        else:
            # Orientación en el club: solo se guía a quien ya tiene categoría confirmada.
            decision = session.get("decision") or {}
            confirmed = decision.get("category") if decision.get("access") in ("authorized", "pending") else None
            guide = club_guide.answer(text, confirmed) if text else None
            if guide:
                understanding = {"intent": guide["intent"], "category_hint": None, "reply": guide["reply"],
                                 "handoff": False, "route": guide["route"]}
            else:
                understanding = dialogue.understand(text) if text else {"intent": "VACIO", "category_hint": None,
                                                                            "reply": None, "handoff": False}
        if understanding["category_hint"] and not session["category_hint"]:
            session["category_hint"] = understanding["category_hint"]
        if understanding["intent"] == "DESCONOCIDO":
            # «¿Podría repetirlo?» como máximo una vez por visita (evita bucles de eco).
            session["unknown_replies"] = session.get("unknown_replies", 0) + 1
            if session["unknown_replies"] > 1:
                understanding = {**understanding, "reply": None}
        evidence_id = None
        if audio_b64 and consent and self.settings.store_evidence:
            evidence_id = self.store_evidence(session, base64.b64decode(audio_b64, validate=True), "audio/wav", "AUDIO")
        transcript = "[dato de identidad omitido]" if step == "identity" else text
        item = {
            "sesion_id": session["id"], "robot_id": session["robot_id"], "texto": transcript, "idioma": language,
            "confianza": confidence, "motor": engine, "inicio": started_at, "fin": ended_at,
            "intencion": understanding["intent"], "evidencia_id": evidence_id,
        }
        session["transcripts"].append(item)
        session["last_activity"] = time.time()
        with self.state.lock:
            self.state.transcripts.appendleft({**item, "created_at": now_iso()})
        self._safe("transcripciones", self.repo.insert, item)
        self._publish("transcript", {"sesion_id": session["id"], "robot_id": session["robot_id"], "texto": transcript,
                                     "idioma": language, "intencion": understanding["intent"]})
        return {**understanding, "speech": understanding["reply"], "ready": ready}

    @staticmethod
    def _retry(session: dict, allowed: int = 1) -> bool:
        """Permite repetir la pregunta de identidad `allowed` veces."""
        session["identity_attempts"] = session.get("identity_attempts", 0) + 1
        return session["identity_attempts"] <= allowed

    def _regular_identity(self, session: dict, persona_id: str, text: str) -> dict:
        """Socio regular: nombre completo + últimos cuatro dígitos del documento + voz registrada.

        Los datos pueden llegar en varias frases; la voz debe coincidir en cada frase que aporta un dato.
        """
        persona = self.repo.persona(persona_id) or {}
        first = (persona.get("nombre") or "").split()[0] if persona.get("nombre") else ""
        words = set(re.findall(r"[a-z0-9]+", dialogue.normalize(text)))
        names = [t for t in re.findall(r"[a-z]+", dialogue.normalize(persona.get("nombre") or "")) if len(t) >= 3]
        tail = "".join(c for c in persona.get("numero_documento") or "" if c.isalnum())[-4:].upper()
        digits = "".join(c for c in text if c.isdigit())
        verified = set(session.get("regular_verified", []))
        given, wrong = set(), []
        if names and all(n in words for n in names):
            given.add("name")
        elif any(n in words for n in names):
            wrong.append("el nombre no coincide con el registro")
        if tail and tail in digits:
            given.add("document")
        elif len(digits) >= 4:
            wrong.append("los dígitos no coinciden con el documento registrado")
        if given or wrong:
            if session.get("voice_identity") == persona_id:
                verified |= given | {"voice"}
                session["identity_voice_similarity"] = session.get("voice_similarity")
            else:  # los datos dichos con otra voz no cuentan
                verified.discard("voice")
                wrong.append("no logré reconocer su voz")
        session["regular_verified"] = sorted(verified)  # la sesión debe seguir siendo serializable
        if {"name", "document", "voice"} <= verified:
            session["dialogue_step"] = "activity"
            session["document_identity"] = persona_id
            session["identity_attempts"] = 0
            reply = (f"Gracias, {first}. Su nombre, su documento y su voz coinciden con el registro. "
                     "¿Qué actividad va a realizar hoy?")
            return {"intent": "IDENTIDAD_CONFIRMADA", "category_hint": "REGULAR", "reply": reply, "handoff": False}
        if not self._retry(session, allowed=2):  # tercer intento fallido: recepción decide
            return {"intent": "IDENTIDAD_NO_CONFIRMADA", "category_hint": "REGULAR", "reply": None,
                    "handoff": True, "ready": True}
        missing = [REGULAR_PARTS[p] for p in ("name", "document") if p not in verified]
        reason = ("Lo siento, " + " y ".join(wrong) + ". ") if wrong else ""
        ask = (f"Por favor, dígame {' y '.join(missing)}." if missing
               else "Por favor, repita su nombre completo con calma para verificar su voz.")
        return {"intent": "IDENTIDAD_PENDIENTE", "category_hint": "REGULAR", "reply": reason + ask, "handoff": False}

    def store_evidence(self, session: dict, content: bytes, mime: str, tipo: str) -> str | None:
        if len(content) > 2_000_000:
            raise ValueError("Evidencia demasiado grande")
        digest = hashlib.sha256(content).hexdigest()
        ext = {"audio/wav": "wav", "image/jpeg": "jpg"}.get(mime, "bin")
        path = f"{session['robot_id']}/{session['id']}/{tipo.lower()}-{digest[:16]}.{ext}"
        try:
            self.repo.upload(self.settings.evidence_bucket, path, content, mime)
        except Exception as error:
            self.state.degraded["storage"] = type(error).__name__
            log.warning("No se pudo subir evidencia: %s", error)
            return None
        evidence_id = str(uuid.uuid4())
        retain = datetime.now(timezone.utc) + timedelta(days=self.settings.evidence_retention_days)
        self._safe("evidencias", self.repo.insert, {
            "id": evidence_id, "sesion_id": session["id"], "tipo": tipo, "bucket": self.settings.evidence_bucket,
            "ruta": path, "mime": mime, "bytes": len(content), "sha256": digest,
            "retener_hasta": retain.isoformat(), "consentimiento": True,
        })
        return evidence_id

    # ---------- decisión ----------

    def best_face(self, session: dict) -> FaceEvidence | None:
        if not session["faces"]:
            return None
        accepted = [f for f in session["faces"] if f["accepted"]]
        if accepted:
            ids = {f["persona_id"] for f in accepted}
            if len(ids) > 1:  # rostros distintos en la misma sesión: dudoso
                return FaceEvidence("__conflict__", 0.0, "conflict")
            best = max(accepted, key=lambda f: f["similarity"])
            return FaceEvidence(best["persona_id"], best["similarity"], best.get("reason", ""),
                                session.get("voice_identity"), session.get("voice_similarity"),
                                session.get("voice_checked", False), session.get("document_identity"),
                                session.get("identity_voice_similarity"))
        return FaceEvidence(None, max(f.get("similarity") or -1 for f in session["faces"]), "unknown")

    def persist_decision(self, decision: Decision, origin: str) -> Decision:
        if decision.persona and decision.persona["categoria"] != "ADMIN":
            ok = self._safe("eventos_acceso", self.repo.insert, {
                "persona_id": decision.persona["id"],
                "categoria": decision.persona["categoria"],
                "tipo_evento": decision.event_type,
                "estado_acceso": ESTADO[decision.access],
                "destino": decision.destination,
                # eventos_acceso solo admite robot1/robot2; el robot físico va en sesiones.
                "robot": decision.robot_target,
                "simulacion": decision.simulation,
            })
            if not ok and decision.access in ("authorized", "pending_escort"):
                decision.access = "review"
                decision.event_type = "access_check"
                decision.robot_target = "robot1"
                decision.reason = "No se pudo registrar la decisión; recepción debe verificar manualmente."
                decision.instruction = "Un miembro de recepción le atenderá en un momento."
        self.audit(origin, "decision", "persona", decision.persona["id"] if decision.persona else "-",
                   {"access": decision.access, "reason": decision.reason, "simulation": decision.simulation})
        return decision

    def route_for(self, decision: Decision) -> dict | None:
        if decision.access not in ("authorized", "pending_escort") or not decision.destination or not decision.category:
            return None
        try:
            route = compute_route(decision.category, decision.destination, escort=decision.escort)
        except RouteError as error:
            return {"error": str(error), "destination": decision.destination}
        token = secrets.token_urlsafe(18)
        expires = datetime.now(timezone.utc) + timedelta(minutes=self.settings.route_share_ttl_min)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        shared = {"route": route, "expires_at": expires.isoformat()}
        with self.state.lock:
            self.state.shared_routes[token_hash] = shared
        self._safe("rutas_compartidas", self.repo.insert, {
            "token_hash": token_hash, "categoria": decision.category, "destino": route["destination_label"],
            "ruta": route, "expira_en": expires.isoformat(),
        })
        route["share_url"] = f"{self.settings.public_app_url}/#/ruta?t={token}"
        route["share_expires_at"] = expires.isoformat()
        return route

    def shared_route(self, token: str) -> dict | None:
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        shared = self.state.shared_routes.get(token_hash)
        if not shared:
            try:
                row = self.repo.one("rutas_compartidas", "token_hash", token_hash)
            except Exception:
                row = None
            if row:
                shared = {"route": row["ruta"], "expires_at": row["expira_en"]}
        if not shared or datetime.fromisoformat(shared["expires_at"].replace("Z", "+00:00")) <= datetime.now(timezone.utc):
            return None
        return shared

    def resolve(self, session: dict) -> dict:
        face = self.best_face(session)
        if face and face.persona_id == "__conflict__":
            decision = Decision("review", "Se detectaron rostros de personas distintas",
                                "Un miembro de recepción le atenderá en un momento.",
                                destination="Recepción", simulation=session["simulation"],
                                checks=[], methods=["facial"])
        else:
            decision = self.engine.evaluate(credential=session["credential"], face=face,
                                            simulation=session["simulation"])
        decision = self.persist_decision(decision, f"robot:{session['robot_id']}")
        route = self.route_for(decision)
        result = {**decision.to_api(), "session_id": session["id"], "route": route,
                  "category_detected": session["category_hint"],
                  "requested_activity": session.get("requested_activity")}
        session["decision"] = result
        session["last_activity"] = time.time()
        self._safe("sesiones_atencion", self.repo.update, "id", session["id"], {
            "persona_id": decision.persona["id"] if decision.persona else None,
            "categoria_detectada": session["category_hint"],
            "categoria_confirmada": decision.category if decision.access in ("authorized", "pending_escort") else None,
            "metodo_verificacion": decision.methods,
            "decision": DECISION[decision.access],
            "justificacion": decision.reason,
            "validaciones": [c.as_dict() for c in decision.checks],
            "destino": decision.destination,
            "credencial_enmascarada": session["credential_masked"],
        })
        with self.state.lock:
            self.state.history.appendleft(self._history_item(session, result))
        self._publish("decision", {"sesion_id": session["id"], "robot_id": session["robot_id"],
                                   "decision": result["decision"], "role": result["role"],
                                   "destination": result["destination"]})
        result["speech"] = self.speech(decision, route)
        if decision.access == "authorized" and session.get("requested_activity"):
            # Acuse de la actividad pedida: cálido con la VIP, sobrio con el regular.
            ack = "¡Con mucho gusto!" if decision.category == "VIP" else "Entendido."
            result["speech"] = f"{ack} {result['speech']}"
        return result

    @staticmethod
    def speech(decision: Decision, route: dict | None) -> str:
        """Lo que dice el robot al decidir: instrucción, indicaciones y cierre por categoría."""
        text = decision.instruction
        if route and "steps" in route:
            minutes = route["minutes"]
            text += (f" Su destino, {route['destination_label']}, está a {route['distance_m']} metros, "
                     f"unos {minutes} minuto{'s' if minutes != 1 else ''} caminando. "
                     f"{club_guide.spoken_steps(route)}")
        closing = CATEGORY_CLOSING.get((decision.category, decision.access))
        if closing:
            text += f" {closing}"
        if route and "steps" in route:
            text += " Puede llevar esta ruta en su celular con el código QR de la pantalla."
        return text

    def _history_item(self, session: dict, result: dict) -> dict:
        return {
            "session_id": session["id"],
            "created_at": now_iso(),
            "display_name": result.get("visitor_name") or "Visitante",
            "role": result.get("role"),
            "category_detected": session["category_hint"],
            "method": " + ".join(result.get("methods") or []) or "—",
            "access": result.get("access"),
            "decision": result.get("decision"),
            "reason": result.get("reason"),
            "destination": result.get("destination"),
            "checks": result.get("checks"),
            "robot_name": session["robot_id"],
            "robot_target": result.get("robot_target"),
            "simulation": result.get("simulation"),
            "transcripts": [t["texto"] for t in session["transcripts"]][-5:],
            "route": result.get("route"),
        }

    def close(self, session_id: str, status: str = "CERRADA") -> None:
        session = self.state.sessions.get(session_id)
        if not session or session["status"] != "ACTIVA":
            return
        session["status"] = status
        self._safe("sesiones_atencion", self.repo.update, "id", session_id,
                   {"estado": status, "finalizada_en": now_iso()})
        self._publish("session", {"id": session_id, "robot_id": session["robot_id"], "estado": status})
        with self.state.lock:
            # Libera memoria de sesiones antiguas.
            for sid in [s for s, v in self.state.sessions.items() if v["status"] != "ACTIVA"][:-20]:
                self.state.sessions.pop(sid, None)

    def public(self, session: dict) -> dict:
        return {
            "id": session["id"], "robot_id": session["robot_id"], "status": session["status"],
            "started_at": session["started_at"], "simulation": session["simulation"],
            "category_hint": session["category_hint"], "credential": session["credential_masked"],
            "faces": len(session["faces"]), "decision": session["decision"],
        }
