"""Identifica la persona en una fotografía: python scripts/recognize_faces.py foto.png"""

import argparse
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nclub_vision.face import FaceEngine  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("photo")
parser.add_argument("--registro", default="dataset/registro")
args = parser.parse_args()
engine = FaceEngine()
engine.enroll_folder(args.registro)
image = cv2.imread(args.photo)
if image is None:
    raise SystemExit("No se pudo abrir la fotografía de prueba")
matches = engine.identify(image)
if not matches:
    print("No se detectó ningún rostro")
for m in matches:
    print(f"Identidad: {m.persona_id or 'unknown'} · similitud {m.score:.3f} · {m.reason}")
