"""Genera un QR de prueba: python scripts/generate_qr.py QR-INV-001 invitado_qr.png"""

import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nclub_vision.qr import encode_qr  # noqa: E402

payload = sys.argv[1] if len(sys.argv) > 1 else "QR-INV-001"
out = sys.argv[2] if len(sys.argv) > 2 else "invitado_qr.png"
cv2.imwrite(out, encode_qr(payload))
print("QR generado:", out)
