"""Vista de desarrollo: reconocimiento facial + QR sobre una fuente de fotogramas.

    python scripts/reconocimiento_tiempo_real.py              # webcam 0 del PC
    python scripts/reconocimiento_tiempo_real.py --folder dataset/pruebas

En el robot no se usa este script: el agente ROS 2 (robot_agent/) entrega
los fotogramas de AimDK a la misma clase FaceEngine.
"""

import argparse
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nclub_vision.face import FaceEngine, draw_matches  # noqa: E402
from nclub_vision.qr import QrReader, draw_qr  # noqa: E402
from nclub_vision.sources import ImageFolderSource, OpenCVCameraSource  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("--camera", type=int, default=0)
parser.add_argument("--folder")
parser.add_argument("--registro", default="dataset/registro")
parser.add_argument("--threshold", type=float)
args = parser.parse_args()

engine = FaceEngine(**({"threshold": args.threshold} if args.threshold else {}))
engine.enroll_folder(args.registro)
print("Personas registradas:", engine.gallery.identities)
qr = QrReader()
source = ImageFolderSource(args.folder, delay=1.5) if args.folder else OpenCVCameraSource(args.camera)
try:
    for frame in source.frames():
        matches = engine.identify(frame, max_faces=3)
        readings = qr.read(frame)
        for r in readings:
            print("QR:", r.kind, r.payload[:16] + "…")
        cv2.imshow("N Club - Reconocimiento", draw_qr(draw_matches(frame, matches), readings))
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break
finally:
    source.close()
    cv2.destroyAllWindows()
