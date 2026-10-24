"""Galería en vivo del nodo ROS: altas, cambios y bajas sin reiniciar el robot.

Usa el código real de ReceptionAgentNode._apply_manifest con ROS simulado y el
backend real en memoria (TestClient) como origen de las fotos.
"""

import shutil
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT / "robot_agent", ROOT / "vision", ROOT / "backend"):
    sys.path.insert(0, str(p))

DATASET = ROOT / "vision" / "dataset"
HAS = (DATASET / "registro").is_dir() and (ROOT / "vision" / "models" / "face_recognition_sface_2021dec.onnx").is_file()


@pytest.mark.skipif(not HAS, reason="requiere vision/dataset y modelos ONNX locales")
def test_new_member_photo_is_recognised_without_restart(tmp_path, monkeypatch):
    from test_tts import install_fake_ros

    install_fake_ros()
    sys.modules.pop("nclub_agent.ros_node", None)
    import cv2
    from fastapi.testclient import TestClient

    from app.config import Settings
    from app.main import create_app
    from app.memory_repo import MemoryRepository
    from nclub_agent.ros_node import ReceptionAgentNode
    from nclub_vision.face import FaceEngine

    faces = tmp_path / "storage"
    shutil.copytree(DATASET / "registro" / "REG001", faces / "REG001")
    settings = Settings()
    settings.mode, settings.robot_api_key = "memory", "live-gallery-key-0123456789"
    repo = MemoryRepository(faces_dir=faces)
    client = TestClient(create_app(settings, repo))
    client.headers["X-Robot-Key"] = settings.robot_api_key

    local = tmp_path / "robot"
    local.mkdir()
    engine = FaceEngine()
    logs = []
    node = NS(registro=str(local), agent=NS(face=engine), client=NS(http=client),
              get_logger=lambda: NS(info=logs.append, warning=logs.append))
    enroller = FaceEngine()

    ReceptionAgentNode._apply_manifest(node, client.get("/robot/gallery").json(), enroller)
    assert engine.gallery.identities == ["REG001"]
    probe = cv2.imread(str(DATASET / "pruebas" / "EXT001" / "foto3.png"))
    assert engine.identify(probe)[0].persona_id is None  # aún no registrado

    # Alta desde la app: nueva persona con foto → versión nueva del manifiesto
    photo = (DATASET / "registro" / "EXT001" / "foto1.png").read_bytes()
    repo.upload_face("MEM-NUEVO", "admin-1.jpg", photo, "image/jpeg")
    client.app.state.ctx.reception.invalidate_gallery()
    ReceptionAgentNode._apply_manifest(node, client.get("/robot/gallery").json(), enroller)
    assert "MEM-NUEVO" in engine.gallery.identities
    assert engine.identify(probe)[0].persona_id == "MEM-NUEVO"
    assert (local / "MEM-NUEVO" / "admin-1.jpg").is_file()

    # Baja: la persona deja de tener fotos → se retira de la galería
    repo.uploaded_faces.clear()
    client.app.state.ctx.reception.invalidate_gallery()
    ReceptionAgentNode._apply_manifest(node, client.get("/robot/gallery").json(), enroller)
    assert engine.gallery.identities == ["REG001"] and not (local / "MEM-NUEVO").exists()
