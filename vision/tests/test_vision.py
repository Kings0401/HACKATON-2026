import shutil
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nclub_vision.models import DETECTOR_PATH, RECOGNIZER_PATH  # noqa: E402
from nclub_vision.qr import QrReader, encode_qr  # noqa: E402
from nclub_vision.sources import QueueFrameSource, decode_jpeg, encode_jpeg, rgb8_to_bgr  # noqa: E402

HAS_MODELS = DETECTOR_PATH.is_file() and RECOGNIZER_PATH.is_file()
DATASET = ROOT / "dataset"
needs_dataset = pytest.mark.skipif(not (HAS_MODELS and (DATASET / "registro").is_dir()),
                                   reason="requiere modelos ONNX y dataset local (no versionados)")


@pytest.mark.parametrize("payload,kind", [("nclub:v1:" + "a" * 64, "secure"), ("QR-INV-001", "static"),
                                          ("demo_123", "demo")])
def test_qr_roundtrip_and_kind(payload, kind):
    readings = QrReader().read(encode_qr(payload))
    assert [r.payload for r in readings] == [payload] and readings[0].kind == kind


def test_qr_inside_a_larger_scene_and_empty_frames():
    scene = np.full((720, 1280, 3), 90, np.uint8)
    qr = encode_qr("CAR-EMP-001", 240)
    scene[200:200 + qr.shape[0], 500:500 + qr.shape[1]] = qr
    assert QrReader().read(scene)[0].payload == "CAR-EMP-001"
    assert QrReader().read(np.zeros((0, 0, 3), np.uint8)) == []


def test_ros_image_conversions():
    rgb = np.zeros((4, 6, 3), np.uint8)
    rgb[..., 0] = 255  # rojo en RGB
    bgr = rgb8_to_bgr(rgb.tobytes(), 6, 4)
    assert bgr[0, 0].tolist() == [0, 0, 255]
    frame = np.full((480, 1280, 3), 128, np.uint8)
    jpeg = encode_jpeg(frame, max_width=640)
    assert jpeg[:2] == b"\xff\xd8" and decode_jpeg(jpeg).shape == (240, 640, 3)


def test_queue_source_keeps_latest_frame():
    source = QueueFrameSource()
    source.push(np.zeros((1, 1, 3)))
    source.push(np.ones((1, 1, 3)))
    frame = next(source.frames())
    source.close()
    assert frame.sum() == 3


@needs_dataset
def test_engine_identifies_test_photos_and_rejects_unenrolled():
    from nclub_vision.face import FaceEngine

    engine = FaceEngine()
    engine.enroll_folder(DATASET / "registro")
    for folder in sorted((DATASET / "pruebas").iterdir()):
        probe = cv2.imread(str(sorted(folder.glob("foto3.png"))[0]))
        match = engine.identify(probe)[0]
        assert match.persona_id == folder.name, (folder.name, match)
    # Visitante no registrado: se retira su identidad de la galería.
    probe = cv2.imread(str(DATASET / "pruebas" / "VIP001" / "foto3.png"))
    engine.gallery.features.pop("VIP001")
    assert engine.identify(probe)[0].persona_id is None


@needs_dataset
def test_duplicate_photo_across_identities_is_excluded(tmp_path):
    from nclub_vision.face import FaceEngine

    for persona in ("REG001", "EMP001"):
        (tmp_path / persona).mkdir()
        shutil.copy(DATASET / "registro" / "VIP001" / "foto1.png", tmp_path / persona / "FOTO.png")
    shutil.copy(DATASET / "registro" / "VIP001" / "foto2.png", tmp_path / "REG001" / "propia.png")
    engine = FaceEngine()
    gallery = engine.enroll_folder(tmp_path)
    assert gallery.identities == ["REG001"] and len(gallery.skipped) == 2


@needs_dataset
def test_no_face_returns_empty():
    from nclub_vision.face import FaceEngine

    engine = FaceEngine()
    assert engine.identify(np.full((480, 640, 3), 200, np.uint8)) == []
