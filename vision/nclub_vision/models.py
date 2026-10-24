"""Rutas y descarga verificada de los modelos ONNX (no se versionan en Git)."""

from __future__ import annotations

import hashlib
import sys
import urllib.request
from pathlib import Path

MODELS_DIR = Path(__file__).resolve().parent.parent / "models"
DETECTOR_PATH = MODELS_DIR / "face_detection_yunet_2023mar.onnx"
RECOGNIZER_PATH = MODELS_DIR / "face_recognition_sface_2021dec.onnx"

# Fuente oficial: OpenCV Zoo. SHA-256 de los archivos entregados en nclub-vision.zip.
MODELS = {
    DETECTOR_PATH: (
        "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
        "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
    ),
    RECOGNIZER_PATH: (
        "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx",
        "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79",
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ensure_models() -> None:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    for path, (url, digest) in MODELS.items():
        if path.is_file() and sha256(path) == digest:
            print(f"OK {path.name}")
            continue
        print(f"Descargando {path.name}…")
        tmp = path.with_suffix(".part")
        urllib.request.urlretrieve(url, tmp)
        if sha256(tmp) != digest:
            tmp.unlink(missing_ok=True)
            sys.exit(f"Hash inesperado para {path.name}; descarga descartada.")
        tmp.replace(path)
        print(f"OK {path.name}")


if __name__ == "__main__":
    ensure_models()
