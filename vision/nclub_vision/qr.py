"""Lectura de QR sobre fotogramas en memoria (sin cámara propia)."""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

SECURE_PREFIX = "nclub:v1:"


@dataclass
class QrReading:
    payload: str
    points: np.ndarray | None

    @property
    def kind(self) -> str:
        """secure: token opaco emitido por emitir_credencial; demo: jamás válido."""
        if self.payload.startswith(SECURE_PREFIX):
            return "secure"
        if self.payload.lower().startswith("demo_"):
            return "demo"
        return "static"


class QrReader:
    def __init__(self) -> None:
        self.detector = cv2.QRCodeDetector()

    def read(self, frame: np.ndarray) -> list[QrReading]:
        if frame is None or frame.size == 0:
            return []
        try:
            ok, payloads, points, _ = self.detector.detectAndDecodeMulti(frame)
        except cv2.error:
            ok, payloads, points = False, (), None
        readings = []
        if ok:
            for i, payload in enumerate(payloads):
                if payload:
                    readings.append(QrReading(payload.strip(), None if points is None else points[i]))
        if not readings:
            payload, pts, _ = self.detector.detectAndDecode(frame)
            if payload:
                readings.append(QrReading(payload.strip(), pts))
        # Limita tamaño: un QR legítimo de N Club nunca supera 100 caracteres.
        return [r for r in readings if 0 < len(r.payload) <= 200]


def encode_qr(payload: str, size: int = 360) -> np.ndarray:
    """Genera un QR BGR (pruebas y simulador)."""
    encoder = cv2.QRCodeEncoder.create()
    qr = encoder.encode(payload)
    qr = cv2.resize(qr, (size, size), interpolation=cv2.INTER_NEAREST)
    qr = cv2.copyMakeBorder(qr, 40, 40, 40, 40, cv2.BORDER_CONSTANT, value=255)
    return cv2.cvtColor(qr, cv2.COLOR_GRAY2BGR)


def draw_qr(frame: np.ndarray, readings: list[QrReading]) -> np.ndarray:
    out = frame.copy()
    for r in readings:
        if r.points is not None:
            pts = r.points.astype(int).reshape(-1, 2)
            cv2.polylines(out, [pts], True, (0, 255, 0), 3)
    return out
