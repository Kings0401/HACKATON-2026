"""Lógica del agente de recepción, independiente de ROS 2.

El nodo ROS (ros_node.py), el simulador (sim.py) y las pruebas comparten esta
clase. No ejecuta movimientos: solo percibe, consulta a FastAPI y habla.
"""

from __future__ import annotations

import base64
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol

import numpy as np

from .backend_client import BackendClient, BackendError, BackendUnavailable
from .speech import NullTranscriber, Transcriber, pcm_to_wav

log = logging.getLogger(__name__)

OFFLINE_MESSAGE = "Disculpe, tengo un problema de conexión. Un miembro de recepción le atenderá enseguida."
# Frases que Whisper suele "oír" en el ruido o en el silencio.
PHANTOM = ("gracias", "subtitulos", "subtítulos", "amara.org", "suscribete", "suscríbete", "musica", "música")


def is_phantom(text: str) -> bool:
    clean = text.strip().lower().strip(".,¡!¿? ")
    return len(clean) < 3 or any(clean.startswith(p) for p in PHANTOM) and len(clean.split()) <= 3


class Speaker(Protocol):
    def speak(self, text: str) -> None: ...


class LogSpeaker:
    def __init__(self) -> None:
        self.spoken: list[str] = []

    def speak(self, text: str) -> None:
        self.spoken.append(text)
        log.info("ROBOT DICE: %s", text)


@dataclass
class AgentConfig:
    analyze_every_s: float = 0.25
    upload_every_s: float = 0.2
    absent_timeout_s: float = 6.0
    face_report_every_s: float = 1.0
    simulated: bool = False
    store_audio: bool = False  # solo con consentimiento y política del club


class FaceTracker:
    """Votación entre fotogramas: una identidad se acepta solo si coincide en
    `needed` de los últimos `window` fotogramas nítidos (y recientes)."""

    def __init__(self, window: int = 3, needed: int = 2, max_age_s: float = 2.5):
        self.window, self.needed, self.max_age_s = window, needed, max_age_s
        self.votes: list[tuple[float, object]] = []

    def add(self, match, now: float):
        self.votes = [(t, m) for t, m in self.votes if now - t <= self.max_age_s][-(self.window - 1):]
        self.votes.append((now, match))
        recent = [m for _, m in self.votes]
        counts: dict[str, list] = {}
        for m in recent:
            if m.persona_id:
                counts.setdefault(m.persona_id, []).append(m)
        for matches in counts.values():
            if len(matches) >= self.needed:
                return max(matches, key=lambda m: m.score)
        if len(recent) >= self.window and not counts:
            return recent[-1]  # varios fotogramas seguidos sin coincidencia: desconocido
        return None  # todavía sin consenso


@dataclass
class AgentState:
    session_id: str | None = None
    decision: dict | None = None
    last_presence: float = 0.0
    last_face_report: float = 0.0
    last_face_id: str | None = None
    credentials_sent: set = field(default_factory=set)
    resolved_at: float = 0.0
    tracker: FaceTracker = field(default_factory=FaceTracker)


class ReceptionAgent:
    def __init__(self, client: BackendClient, face_engine=None, qr_reader=None, speaker: Speaker | None = None,
                 transcriber: Transcriber | None = None, config: AgentConfig | None = None,
                 on_decision: Callable[[dict], None] | None = None, encode_jpeg: Callable | None = None,
                 clock: Callable[[], float] = time.monotonic):
        self.client = client
        self.face = face_engine
        self.qr = qr_reader
        self.speaker = speaker or LogSpeaker()
        self.transcriber = transcriber or NullTranscriber()
        self.config = config or AgentConfig()
        self.on_decision = on_decision
        self.encode_jpeg = encode_jpeg
        self.clock = clock
        self.state = AgentState()
        self.lock = threading.RLock()
        self._last_analysis = -1e9
        self._last_upload = -1e9
        self.camera_ok = False
        self.mic_ok = False
        self.mic_state = "desconocido"
        self.last_frame_at = 0.0
        self.last_audio_at = 0.0
        self.last_matches: list = []
        self.last_readings: list = []
        self.speaking_until = 0.0  # mientras el robot habla, no se escucha a sí mismo
        self.on_session_start: Callable[[], None] | None = None  # p. ej. gesto de saludo

    # ---------- estado para el latido ----------

    def status(self) -> dict:
        now = self.clock()
        return {
            "camera_ok": self.camera_ok and now - self.last_frame_at < 5,
            "mic_ok": self.mic_ok and now - self.last_audio_at < 30,
            "mic_state": self.mic_state,
            "simulated": self.config.simulated,
        }

    def _say(self, text: str | None) -> None:
        if text:
            # Duración estimada de la voz (~13 caracteres/s) más un margen de eco.
            start = max(self.clock(), self.speaking_until)
            self.speaking_until = start + 1.5 + len(text) * 0.075
            self.speaker.speak(text)

    # ---------- sesión ----------

    def _ensure_session(self) -> str | None:
        if self.state.session_id:
            return self.state.session_id
        try:
            self.state.session_id = self.client.start_session(self.config.simulated)["id"]
            self._say("Bienvenido a N Club. Será un placer atenderle.")
            if self.on_session_start:
                self.on_session_start()
        except BackendError:
            self._say(OFFLINE_MESSAGE)
            return None
        return self.state.session_id

    def end_session(self) -> None:
        with self.lock:
            if self.state.session_id:
                try:
                    self.client.close(self.state.session_id)
                except BackendError:
                    pass
            self.state = AgentState()

    def _resolve(self) -> dict | None:
        try:
            decision = self.client.resolve(self.state.session_id)
        except BackendUnavailable:
            self._say(OFFLINE_MESSAGE)
            return None
        except BackendError as error:
            log.warning("Resolución rechazada: %s", error)
            return None
        self.state.decision = decision
        self.state.resolved_at = self.clock()
        self._say(decision.get("speech") or decision.get("instruction"))
        if self.on_decision:
            self.on_decision(decision)
        return decision

    # ---------- visión ----------

    def on_frame(self, frame: np.ndarray) -> dict | None:
        """Procesa un fotograma BGR. Devuelve la decisión si se produjo una."""
        now = self.clock()
        self.camera_ok, self.last_frame_at = True, now
        if self.encode_jpeg and now - self._last_upload >= self.config.upload_every_s:
            self._last_upload = now
            try:
                self.client.push_frame(self.encode_jpeg(frame))
            except BackendError:
                pass
        if now - self._last_analysis < self.config.analyze_every_s:
            return None
        self._last_analysis = now
        with self.lock:
            self.tick()
            matches = self.face.identify(frame) if self.face else []
            readings = self.qr.read(frame) if self.qr else []
            # Para superponer recuadros en la vista de cámara (robot simulado).
            self.last_matches, self.last_readings = matches, readings
            if not matches and not readings:
                return None
            self.state.last_presence = now
            if self.state.decision:
                return None  # ya atendido; espera a que el visitante se retire
            if not self._ensure_session():
                return None
            # Rostros movidos o desenfocados no votan (sí cuentan como presencia).
            sharp = [m for m in matches if m.reason != "blurry"]
            best = self.state.tracker.add(sharp[0], now) if sharp else None
            if best is not None:
                changed = best.persona_id != self.state.last_face_id
                if changed or now - self.state.last_face_report >= self.config.face_report_every_s:
                    self.state.last_face_id = best.persona_id
                    self.state.last_face_report = now
                    try:
                        reply = self.client.face(self.state.session_id, best.as_observation(self.face.threshold))
                        if changed:
                            self._say(reply.get("speech"))
                    except BackendError:
                        pass
            for reading in readings:
                if reading.payload in self.state.credentials_sent:
                    continue
                self.state.credentials_sent.add(reading.payload)
                try:
                    self.client.credential(self.state.session_id, reading.payload, reading.kind)
                except BackendError:
                    self._say(OFFLINE_MESSAGE)
                    return None
                return self._resolve()
        return None

    # ---------- voz ----------

    def on_utterance(self, pcm: bytes, started_at: str | None = None, consent: bool = False) -> dict | None:
        self.last_audio_at = self.clock()
        self.mic_ok = True
        if self.clock() < self.speaking_until:
            log.info("Audio descartado: el robot estaba hablando (eco)")
            return None
        text, confidence = self.transcriber.transcribe(pcm)
        if is_phantom(text):
            return None
        return self.on_text(text, confidence, self.transcriber.name, started_at,
                            audio=pcm if (consent and self.config.store_audio) else None)

    def on_text(self, text: str, confidence: float | None = None, engine: str = "manual",
                started_at: str | None = None, audio: bytes | None = None) -> dict | None:
        if not text.strip():
            return None
        with self.lock:
            self.state.last_presence = self.clock()
            if not self._ensure_session():
                return None
            body = {
                "text": text, "language": "es-CO", "confidence": confidence, "engine": engine,
                "started_at": started_at, "ended_at": datetime.now(timezone.utc).isoformat(),
            }
            if audio:
                body.update(audio_wav_b64=base64.b64encode(pcm_to_wav(audio)).decode(), consent=True)
            try:
                reply = self.client.utterance(self.state.session_id, **body)
            except BackendError:
                self._say(OFFLINE_MESSAGE)
                return None
            # Tras decidir, el robot sigue respondiendo preguntas de orientación.
            if not self.state.decision or reply.get("intent") in ("UBICACION", "ESPACIOS"):
                self._say(reply.get("speech"))
            return reply

    def on_mic_state(self, state: str) -> None:
        self.mic_ok, self.mic_state, self.last_audio_at = True, state, self.clock()

    # ---------- tiempo ----------

    def tick(self) -> None:
        now = self.clock()
        if not self.state.session_id:
            return
        absent_for = now - self.state.last_presence
        if self.state.decision:
            # Atendido: se cierra cuando la persona se retira (o tras 60 s),
            # para no repetir la decisión con el mismo QR aún visible.
            done = absent_for > min(2.0, self.config.absent_timeout_s) or now - self.state.resolved_at > 60
        else:
            done = absent_for > self.config.absent_timeout_s
        if done:
            self.end_session()
