"""Robot simulado con cámara del dispositivo, alta de miembros y fotos de registro."""

from pathlib import Path

import cv2
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "vision" / "dataset"
MODELS = ROOT / "vision" / "models" / "face_recognition_sface_2021dec.onnx"
needs_faces = pytest.mark.skipif(not (DATASET.is_dir() and MODELS.is_file()),
                                 reason="requiere vision/dataset y modelos ONNX locales")


def jpeg(path_or_image) -> bytes:
    image = cv2.imread(str(path_or_image)) if isinstance(path_or_image, Path) else path_or_image
    return cv2.imencode(".jpg", image)[1].tobytes()


@pytest.fixture
def lab_client(settings, admin):
    """Backend en memoria con la galería real de vision/dataset/registro."""
    from fastapi.testclient import TestClient

    from app.main import create_app
    from app.memory_repo import MemoryRepository

    repo = MemoryRepository(faces_dir=DATASET / "registro", admin_token=admin["Authorization"].split()[1])
    return TestClient(create_app(settings, repo)), repo


def test_lab_requires_admin(client):
    assert client.post("/admin/lab/frame", content=b"\xff\xd8").status_code == 401
    assert client.post("/admin/members", json={}).status_code == 401


@needs_faces
def test_device_camera_recognizes_face_then_qr_decides(lab_client, admin):
    from nclub_vision.qr import encode_qr

    client, repo = lab_client
    face = client.post("/admin/lab/frame", content=jpeg(DATASET / "pruebas" / "VIP001" / "foto3.png"),
                       headers={**admin, "Content-Type": "image/jpeg"}).json()
    assert face["simulation"] is True
    assert face["faces"][0]["persona_id"] == "VIP001" and face["faces"][0]["similarity"] >= 0.62
    assert any("Valeria" in s for s in face["speech"])  # saludo personalizado; aún sin acceso
    assert face["decision"] is None
    voice = client.post("/admin/lab/text", json={"text": "Buenos días, soy socia VIP"}, headers=admin).json()
    assert voice["intent"] == "VIP" and voice["speech"]
    qr = client.post("/admin/lab/frame", content=jpeg(encode_qr("NFC-VIP-001")),
                     headers={**admin, "Content-Type": "image/jpeg"}).json()
    assert qr["decision"]["decision"] == "AUTORIZADO" and qr["decision"]["robot_target"] == "robot2"
    assert qr["decision"]["route"]["destination"] == "lounge_vip"
    monitor = client.get("/robot/monitor", headers=admin).json()
    assert monitor["device_camera_active"] and not monitor["agibot_connected"]
    assert monitor["events"][0]["robot_name"] == "camara-dispositivo"


@needs_faces
def test_new_member_photo_enables_recognition_and_access(lab_client, admin):
    from nclub_vision.qr import encode_qr

    client, repo = lab_client
    created = client.post("/admin/members", json={"nombre": "Ana Prueba", "categoria": "VIP",
                                                  "vigencia_hasta": "2027-12-31"}, headers=admin)
    assert created.status_code == 200, created.text
    member = created.json()
    pid = member["persona_id"]
    assert member["credential"]["token"] and repo.membership(pid)["nivel"] == "VIP"
    # Una persona nueva: se reutiliza el rostro de prueba de EXT001 retirándolo de la galería.
    lab = client.app.state.ctx.gallery
    lab.get().gallery.features.pop("EXT001")
    photo = jpeg(DATASET / "registro" / "EXT001" / "foto1.png")
    assert client.post(f"/admin/personas/{pid}/photos", content=photo, headers=admin).status_code == 400  # sin consentimiento
    up = client.post(f"/admin/personas/{pid}/photos?consent=true", content=photo,
                     headers={**admin, "Content-Type": "image/jpeg"})
    assert up.status_code == 200 and up.json()["enrolled"] is True
    assert repo.face_files(pid) == [up.json()["file"]]
    seen = client.post("/admin/lab/frame", content=jpeg(DATASET / "pruebas" / "EXT001" / "foto3.png"),
                       headers={**admin, "Content-Type": "image/jpeg"}).json()
    assert seen["faces"][0]["persona_id"] == pid
    decided = client.post("/admin/lab/frame", content=jpeg(encode_qr("nclub:v1:" + member["credential"]["token"])),
                          headers={**admin, "Content-Type": "image/jpeg"}).json()
    assert decided["decision"]["decision"] == "AUTORIZADO" and decided["decision"]["visitor_id"] == pid
    assert "facial" in decided["decision"]["methods"]


@needs_faces
def test_photo_without_exactly_one_face_is_rejected(lab_client, admin):
    client, _ = lab_client
    blank = jpeg(np.full((480, 640, 3), 220, np.uint8))
    r = client.post("/admin/personas/REG001/photos?consent=true", content=blank, headers=admin)
    assert r.status_code == 422 and "exactamente un rostro" in r.json()["detail"]


def test_member_validation(client, admin):
    bad = client.post("/admin/members", json={"nombre": "Ana", "categoria": "VIP", "vigencia_hasta": "2020-01-01"},
                      headers=admin)
    assert bad.status_code == 422
    assert client.post("/admin/members", json={"nombre": "Ana", "categoria": "INVITADO",
                                               "vigencia_hasta": "2027-01-01"}, headers=admin).status_code == 422


def test_failed_membership_insert_rolls_back_person(client, admin, repo):
    repo.fail_tables.add("membresias")
    before = len(repo.tables["personas"])
    r = client.post("/admin/members", json={"nombre": "Ana Prueba", "categoria": "REGULAR",
                                            "vigencia_hasta": "2027-12-31"}, headers=admin)
    assert r.status_code == 503 and len(repo.tables["personas"]) == before
