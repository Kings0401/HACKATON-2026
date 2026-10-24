"""Robot SIMULADO: recorre los cinco flujos con imágenes del dataset, QR
generados y frases de texto, usando el mismo ReceptionAgent que el nodo ROS.

    python -m nclub_agent.sim --backend http://127.0.0.1:8000

No accede a cámaras ni micrófonos. Requiere un backend; para no tocar datos
reales use NCLUB_BACKEND_MODE=memory en el backend. Las sesiones se marcan
simuladas.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

import cv2
import numpy as np

from nclub_vision.face import FaceEngine
from nclub_vision.qr import QrReader, encode_qr
from nclub_vision.sources import encode_jpeg

from .backend_client import BackendClient
from .core import AgentConfig, LogSpeaker, ReceptionAgent

VISION = Path(__file__).resolve().parents[2] / "vision"
SCENARIOS = [
    ("VIP", "VIP001", "Buenos días, soy socia VIP", "NFC-VIP-001"),
    ("REGULAR", "REG001", "Hola, tengo una reserva de golf", "APP-REG-001"),
    ("INVITADO", "INV001", "Soy invitada de Valeria Torres", "QR-INV-001"),
    ("PERSONAL", "EMP001", "Buenos días, vengo a mi turno", "CAR-EMP-001"),
    ("PROVEEDOR", "EXT001", "Vengo por una orden de mantenimiento", "QR-EXT-001"),
]


def probe_image(persona_id: str) -> np.ndarray | None:
    folder = VISION / "dataset" / "pruebas" / persona_id
    files = sorted(folder.glob("*.png")) if folder.is_dir() else []
    return cv2.imread(str(files[0])) if files else None


def run(backend: str, robot_key: str, robot_id: str = "robot-sim", with_faces: bool = True,
        client: BackendClient | None = None, clock=None) -> list[dict]:
    engine = None
    if with_faces and (VISION / "dataset" / "registro").is_dir():
        engine = FaceEngine()
        engine.enroll_folder(VISION / "dataset" / "registro")
    t = [0.0]
    agent = ReceptionAgent(
        client or BackendClient(backend, robot_key, robot_id), engine, QrReader(), LogSpeaker(),
        config=AgentConfig(simulated=True, analyze_every_s=0, upload_every_s=0),
        encode_jpeg=encode_jpeg, clock=clock or (lambda: t[0]),
    )
    results = []
    for label, persona_id, phrase, credential in SCENARIOS:
        t[0] += 1
        face = probe_image(persona_id) if engine else None
        if face is not None:
            agent.on_frame(face)
            t[0] += 1
        agent.on_text(phrase, 0.9, "simulado")
        t[0] += 1
        decision = agent.on_frame(encode_qr(credential))
        results.append({"scenario": label, **(decision or {"access": "sin decisión"})})
        t[0] += 30  # el visitante se retira
        agent.tick()
    return results


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # consola de Windows
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", default=os.environ.get("NCLUB_API_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--robot-id", default="robot-sim")
    parser.add_argument("--no-faces", action="store_true")
    args = parser.parse_args()
    key = os.environ.get("NCLUB_ROBOT_KEY") or os.environ.get("ROBOT_API_KEY", "")
    for r in run(args.backend, key, args.robot_id, not args.no_faces):
        route = r.get("route") or {}
        print(f"{r['scenario']:<10} {r.get('decision', r['access']):<15} {r.get('destination') or '—':<26} "
              f"{' → '.join(route.get('path', [])) or '—'}")
        time.sleep(0.2)


if __name__ == "__main__":
    main()
