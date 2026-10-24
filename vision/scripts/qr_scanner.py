"""Lector QR de desarrollo (webcam o imagen): python scripts/qr_scanner.py [--image qr.png]"""

import argparse
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nclub_vision.qr import QrReader  # noqa: E402
from nclub_vision.sources import OpenCVCameraSource  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("--image")
parser.add_argument("--camera", type=int, default=0)
args = parser.parse_args()
reader = QrReader()
if args.image:
    for r in reader.read(cv2.imread(args.image)):
        print(r.kind, r.payload)
    raise SystemExit
source = OpenCVCameraSource(args.camera)
try:
    for frame in source.frames():
        readings = reader.read(frame)
        if readings:
            print("¡Código QR detectado!", readings[0].kind, readings[0].payload)
            break
        cv2.imshow("N Club - Lector QR", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break
finally:
    source.close()
    cv2.destroyAllWindows()
