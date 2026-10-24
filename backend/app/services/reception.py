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
    ("VIP", "authorized"): "Mi compañero AGIBOT 02 le acompañará para una atención personalizada.",
    ("REGULAR", "authorized"): "Que disfrute su visita en N Club.",
    ("INVITADO", "authorized"): "Su anfitrión ya fue notificado; la ruta solo incluye las áreas de su invitación.",
    ("PERSONAL_INTERNO", "authorized"): "Recuerde llevar su carné visible durante el turno.",
    ("TRABAJADOR_EXTERNO", "pending_escort"): "Por seguridad, permanezca en la recepción de proveedores hasta que llegue su acompañante y no ingrese a áreas sociales.",
}


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
        if candidate and candidate["activo"]:
            first = candidate["nombre"].split()[0]
            # Saludo ágil: personaliza la atención pero NO autoriza.
            greeting = f"Hola, {first}. Para confirmar su ingreso, muestre su credencial, por favor."
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
                      audio_b64: str | None = None, consent: bool = False) -> dict:
        text = text.strip()[:1000]
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
        item = {
            "sesion_id": session["id"], "robot_id": session["robot_id"], "texto": text, "idioma": language,
            "confianza": confidence, "motor": engine, "inicio": started_at, "fin": ended_at,
            "intencion": understanding["intent"], "evidencia_id": evidence_id,
        }
        session["transcripts"].append(item)
        session["last_activity"] = time.time()
        with self.state.lock:
            self.state.transcripts.appendleft({**item, "created_at": now_iso()})
        self._safe("transcripciones", self.repo.insert, item)
        self._publish("transcript", {"sesion_id": session["id"], "robot_id": session["robot_id"], "texto": text,
                                     "idioma": language, "intencion": understanding["intent"]})
        return {**understanding, "speech": understanding["reply"]}

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
            return FaceEvidence(best["persona_id"], best["similarity"], best.get("reason", ""))
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
                  "category_detected": session["category_hint"]}
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
