"""Robot simulado con la cámara del dispositivo del ADMIN.

Cuando no hay un AGIBOT conectado, el navegador ADMIN envía fotogramas de su
propia cámara. Aquí se procesan con el MISMO ReceptionAgent del robot (rostro,
QR, voz, sesiones, decisión y ruta) mediante un cliente en proceso. Todo se
marca como simulación y los fotogramas no se guardan.
"""

from __future__ import annotations

import logging
import sys
import threading
import time
from pathlib import Path

import cv2
import numpy as np

from ..repository import Repository
from .reception import ReceptionService

log = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[3]
for folder in (ROOT / "vision", ROOT / "robot_agent"):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

from nclub_agent.backend_client import BackendError  # noqa: E402
from nclub_agent.core import AgentConfig, ReceptionAgent  # noqa: E402

DEVICE_ROBOT = "camara-dispositivo"


class LabUnavailable(RuntimeError):
    pass


class FaceGallery:
    """FaceEngine compartido, alimentado desde Storage (rostros-nclub)."""

    def __init__(self, repo: Repository, threshold: float):
        self.repo = repo
        self.threshold = threshold
        self.lock = threading.RLock()
        self.engine = None
        self.loaded_at = 0.0
        self.skipped: list[str] = []

    def get(self):
        with self.lock:
            if self.engine is None:
                self.engine = self._load()
            return self.engine

    def _load(self):
        try:
            from nclub_vision.face import FaceEngine

            engine = FaceEngine(threshold=self.threshold)
        except FileNotFoundError as error:
            raise LabUnavailable(f"{error}. Ejecute: python -m nclub_vision.models") from error
        except ImportError as error:
            raise LabUnavailable("Falta OpenCV en el backend: pip install -r requirements.txt") from error
        self.skipped = []
        for persona_id in self.repo.face_folders():
            for name in self.repo.face_files(persona_id):
                self._enroll(engine, persona_id, name)
        self.loaded_at = time.time()
        log.info("Galería facial cargada: %s", engine.gallery.identities)
        return engine

    def _enroll(self, engine, persona_id: str, name: str) -> bool:
        try:
            image = cv2.imdecode(np.frombuffer(self.repo.download_face(persona_id, name), np.uint8), cv2.IMREAD_COLOR)
        except Exception as error:
            self.skipped.append(f"{persona_id}/{name}: {type(error).__name__}")
            return False
        if image is None or not engine.enroll_image(persona_id, image):
            self.skipped.append(f"{persona_id}/{name}: sin exactamente un rostro")
            return False
        return True

    def add(self, persona_id: str, image: np.ndarray) -> bool:
        with self.lock:
            return self.get().enroll_image(persona_id, image)

    def count_faces(self, image: np.ndarray) -> int:
        with self.lock:
            return len(self.get().detect(image))

    def reload(self) -> None:
        with self.lock:
            self.engine = None
            self.get()

    def status(self) -> dict:
        engine = self.engine
        return {
            "loaded": engine is not None,
            "identities": {k: len(v) for k, v in engine.gallery.features.items()} if engine else {},
            "skipped": self.skipped[-20:],
            "threshold": self.threshold,
        }


class InProcessClient:
    """Implementa la interfaz de BackendClient llamando al servicio directamente."""

    def __init__(self, reception: ReceptionService, robot_id: str):
        self.reception = reception
        self.robot_id = robot_id
        self.online = True

    def _session(self, session_id: str) -> dict:
        session = self.reception.get(session_id)
        if not session or session["status"] != "ACTIVA":
            raise BackendError("Sesión terminada")
        return session

    def start_session(self, simulated: bool = True) -> dict:
        return self.reception.start(self.robot_id, simulated=True)

    def face(self, session_id: str, observation: dict) -> dict:
        return self.reception.add_face(self._session(session_id), observation)

    def credential(self, session_id: str, payload: str, kind: str) -> dict:
        return self.reception.add_credential(self._session(session_id), payload, kind)

    def utterance(self, session_id: str, **body) -> dict:
        return self.reception.add_utterance(
            self._session(session_id), body.get("text", ""), body.get("language", "es-CO"),
            body.get("confidence"), body.get("engine"), body.get("started_at"), body.get("ended_at"),
        )

    def resolve(self, session_id: str) -> dict:
        session = self._session(session_id)
        return session["decision"] or self.reception.resolve(session)

    def close(self, session_id: str) -> dict:
        self.reception.close(session_id)
        return {"closed": True}

    def push_frame(self, jpeg: bytes) -> None:
        with self.reception.state.lock:
            self.reception.state.frames[self.robot_id] = (jpeg, time.time())

    def heartbeat(self, **status) -> dict:
        return self.reception.heartbeat(self.robot_id, status)


class CollectSpeaker:
    def __init__(self) -> None:
        self.pending: list[str] = []

    def speak(self, text: str) -> None:
        self.pending.append(text)

    def drain(self) -> list[str]:
        spoken, self.pending = self.pending, []
        return spoken


class DeviceLab:
    """Un robot simulado por ADMIN (cada navegador tiene su propia sesión)."""

    def __init__(self, reception: ReceptionService, gallery: FaceGallery):
        self.reception = reception
        self.gallery = gallery
        self.robots: dict[str, tuple[ReceptionAgent, CollectSpeaker]] = {}
        self.lock = threading.Lock()

    def _robot(self, admin_id: str):
        with self.lock:
            if admin_id not in self.robots:
                from nclub_vision.qr import QrReader

                speaker = CollectSpeaker()
                agent = ReceptionAgent(
                    InProcessClient(self.reception, DEVICE_ROBOT), self.gallery.get(), QrReader(), speaker,
                    config=AgentConfig(analyze_every_s=0, upload_every_s=0.3, simulated=True),
                    encode_jpeg=lambda frame: _jpeg(frame),
                )
                self.robots[admin_id] = (agent, speaker)
            return self.robots[admin_id]

    def frame(self, admin_id: str, jpeg: bytes) -> dict:
        image = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("El fotograma no es una imagen válida")
        agent, speaker = self._robot(admin_id)
        with self.gallery.lock:  # FaceRecognizerSF no es seguro entre hilos
            decision = agent.on_frame(image)
        agent.client.heartbeat(name="Cámara del dispositivo (simulación)", model="Navegador ADMIN",
                               camera_ok=True, mic_ok=agent.mic_ok, mic_state=agent.mic_state, simulated=True)
        return self._result(agent, speaker, decision, image.shape)

    def text(self, admin_id: str, text: str) -> dict:
        agent, speaker = self._robot(admin_id)
        agent.on_mic_state("procesando")
        reply = agent.on_text(text, None, "navegador (Web Speech)")
        agent.on_mic_state("escuchando")
        return {**self._result(agent, speaker, None, None), "intent": (reply or {}).get("intent")}

    def reset(self, admin_id: str) -> None:
        with self.lock:
            robot = self.robots.pop(admin_id, None)
        if robot:
            robot[0].end_session()

    @staticmethod
    def _result(agent: ReceptionAgent, speaker: CollectSpeaker, decision: dict | None, shape) -> dict:
        return {
            "simulation": True,
            "session_id": agent.state.session_id,
            "frame": {"width": shape[1], "height": shape[0]} if shape else None,
            "faces": [
                {"box": list(m.box), "persona_id": m.persona_id, "similarity": round(float(m.score), 3),
                 "reason": m.reason} for m in agent.last_matches
            ] if shape else [],
            "qr": [{"kind": r.kind} for r in agent.last_readings] if shape else [],
            "speech": speaker.drain(),
            "decision": decision or agent.state.decision,
        }


def _jpeg(frame: np.ndarray) -> bytes:
    ok, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
    return buffer.tobytes() if ok else b""
