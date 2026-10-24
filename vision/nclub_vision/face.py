"""Reconocimiento facial reutilizable (YuNet + SFace) sobre fotogramas en memoria.

No abre cámaras: recibe matrices BGR de cualquier origen (ROS 2, archivo,
webcam de desarrollo). Una coincidencia facial es solo una identidad
candidata; la autorización la decide FastAPI con credenciales y Supabase.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from .models import DETECTOR_PATH, RECOGNIZER_PATH

log = logging.getLogger(__name__)

IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png")

# Provisional, calibrado con dataset/registro vs dataset/pruebas (ver
# calibrate.py y docs/VISION.md): genuinos >= 0.634; un visitante no
# registrado llegó a 0.603, así que 0.363 y 0.50 lo aceptaban. El margen exige
# que la mejor identidad supere claramente a la segunda.
DEFAULT_THRESHOLD = 0.62
DEFAULT_MARGIN = 0.06
DEFAULT_MIN_FACE = 60


@dataclass
class FaceMatch:
    persona_id: str | None
    score: float
    box: tuple[int, int, int, int]
    detection_score: float
    second_id: str | None = None
    second_score: float = -1.0
    reason: str = "match"

    @property
    def known(self) -> bool:
        return self.persona_id is not None

    def as_observation(self, threshold: float) -> dict:
        """Formato que el agente envía a FastAPI. Sin imagen ni plantilla."""
        return {
            "persona_id": self.persona_id,
            "similarity": round(float(self.score), 4),
            "threshold": threshold,
            "second_persona_id": self.second_id,
            "second_similarity": round(float(self.second_score), 4),
            "detection_score": round(float(self.detection_score), 4),
            "reason": self.reason,
        }


@dataclass
class Gallery:
    """Plantillas en memoria por persona. Nunca se persisten en la base."""

    features: dict[str, list[np.ndarray]] = field(default_factory=dict)
    skipped: list[str] = field(default_factory=list)

    @property
    def identities(self) -> list[str]:
        return sorted(self.features)

    def add(self, persona_id: str, feature: np.ndarray) -> None:
        self.features.setdefault(persona_id, []).append(feature)


class FaceEngine:
    def __init__(
        self,
        detector_path: str | Path = DETECTOR_PATH,
        recognizer_path: str | Path = RECOGNIZER_PATH,
        threshold: float = DEFAULT_THRESHOLD,
        margin: float = DEFAULT_MARGIN,
        detection_score: float = 0.9,
        min_face: int = DEFAULT_MIN_FACE,
    ):
        for path in (detector_path, recognizer_path):
            if not Path(path).is_file():
                raise FileNotFoundError(
                    f"Modelo no encontrado: {path}. Ejecuta python -m nclub_vision.models"
                )
        self.detector = cv2.FaceDetectorYN.create(
            str(detector_path), "", (320, 320), detection_score, 0.3, 5000
        )
        self.recognizer = cv2.FaceRecognizerSF.create(str(recognizer_path), "")
        self.threshold = threshold
        self.margin = margin
        self.min_face = min_face
        self.gallery = Gallery()

    # ---------- detección y características ----------

    def detect(self, frame: np.ndarray) -> np.ndarray:
        if frame is None or frame.size == 0:
            return np.empty((0, 15), dtype=np.float32)
        height, width = frame.shape[:2]
        self.detector.setInputSize((width, height))
        _, faces = self.detector.detect(frame)
        if faces is None:
            return np.empty((0, 15), dtype=np.float32)
        faces = [f for f in faces if min(f[2], f[3]) >= self.min_face]
        # El rostro más grande primero: es el visitante frente al robot.
        faces.sort(key=lambda f: f[2] * f[3], reverse=True)
        return np.array(faces, dtype=np.float32).reshape(-1, 15)

    def embed(self, frame: np.ndarray, face: np.ndarray) -> np.ndarray:
        aligned = self.recognizer.alignCrop(frame, face)
        return self.recognizer.feature(aligned)

    def similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        return float(self.recognizer.match(a, b, cv2.FaceRecognizerSF_FR_COSINE))

    # ---------- registro ----------

    def enroll_image(self, persona_id: str, image: np.ndarray) -> bool:
        faces = self.detect(image)
        # Una fotografía de registro con 0 o varios rostros es ambigua.
        if len(faces) != 1:
            return False
        self.gallery.add(persona_id, self.embed(image, faces[0]))
        return True

    def enroll_folder(self, root: str | Path) -> Gallery:
        """Registra dataset/registro/<PERSONA_ID>/*.jpg|png.

        Descarta fotografías idénticas asignadas a dos personas distintas:
        con ellas el sistema confundiría identidades sistemáticamente.
        """
        root = Path(root)
        if not root.is_dir():
            raise FileNotFoundError(f"No existe la carpeta de registro {root}")
        owners: dict[str, set[str]] = {}
        files: list[tuple[str, Path, str]] = []
        for folder in sorted(p for p in root.iterdir() if p.is_dir()):
            for file in sorted(folder.iterdir()):
                if file.suffix.lower() not in IMAGE_SUFFIXES:
                    continue
                digest = hashlib.sha256(file.read_bytes()).hexdigest()
                owners.setdefault(digest, set()).add(folder.name)
                files.append((folder.name, file, digest))
        for persona_id, file, digest in files:
            if len(owners[digest]) > 1:
                self.gallery.skipped.append(
                    f"{persona_id}/{file.name}: misma imagen registrada para {sorted(owners[digest])}"
                )
                continue
            image = cv2.imread(str(file))
            if image is None or not self.enroll_image(persona_id, image):
                self.gallery.skipped.append(
                    f"{persona_id}/{file.name}: sin exactamente un rostro legible"
                )
        for warning in self.gallery.skipped:
            log.warning("Registro omitido: %s", warning)
        return self.gallery

    # ---------- identificación ----------

    def best_scores(self, feature: np.ndarray) -> list[tuple[str, float]]:
        scores = [
            (pid, max(self.similarity(feature, stored) for stored in feats))
            for pid, feats in self.gallery.features.items()
        ]
        return sorted(scores, key=lambda item: item[1], reverse=True)

    def identify_face(self, frame: np.ndarray, face: np.ndarray) -> FaceMatch:
        box = tuple(int(v) for v in face[:4])
        ranked = self.best_scores(self.embed(frame, face))
        if not ranked:
            return FaceMatch(None, -1.0, box, float(face[14]), reason="empty_gallery")
        best_id, best = ranked[0]
        second_id, second = ranked[1] if len(ranked) > 1 else (None, -1.0)
        if best < self.threshold:
            return FaceMatch(None, best, box, float(face[14]), best_id, second, "below_threshold")
        if second_id is not None and best - second < self.margin:
            return FaceMatch(None, best, box, float(face[14]), second_id, second, "ambiguous")
        return FaceMatch(best_id, best, box, float(face[14]), second_id, second)

    def identify(self, frame: np.ndarray, max_faces: int = 1) -> list[FaceMatch]:
        return [self.identify_face(frame, f) for f in self.detect(frame)[:max_faces]]


def draw_matches(frame: np.ndarray, matches: list[FaceMatch]) -> np.ndarray:
    """Superpone recuadros para la vista de desarrollo o el stream ADMIN."""
    out = frame.copy()
    for m in matches:
        x, y, w, h = m.box
        color = (80, 220, 120) if m.known else (60, 60, 230)
        cv2.rectangle(out, (x, y), (x + w, y + h), color, 2)
        label = f"{m.persona_id or 'DESCONOCIDO'} ({m.score:.2f})"
        cv2.putText(out, label, (x, max(y - 10, 20)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
    return out
