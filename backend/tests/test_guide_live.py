"""Guía del club por voz, galería en vivo y estado público del robot."""

import pytest

from app.services import club_guide


def session(client, robot, credential=None, texts=()):
    sid = client.post("/robot/sessions", json={"robot_id": "robot1"}, headers=robot).json()["id"]
    if credential:
        client.post(f"/robot/sessions/{sid}/credentials", json={"payload": credential}, headers=robot)
        decision = client.post(f"/robot/sessions/{sid}/resolve", headers=robot).json()
    else:
        decision = None
    replies = [client.post(f"/robot/sessions/{sid}/utterances", json={"text": t}, headers=robot).json()
               for t in texts]
    return decision, replies


@pytest.mark.parametrize("text,node", [
    ("¿Dónde queda el restaurante?", "restaurante"),
    ("cómo llego a la cancha dos", "cancha_2"),
    ("dónde está el lounge", "lounge_vip"),
    ("necesito ir a la zona técnica", "zona_tecnica"),
])
def test_places_are_recognised(text, node):
    assert club_guide.find_place(club_guide.normalize(text)) == node


def test_unverified_visitor_gets_description_not_route():
    r = club_guide.answer("¿Dónde queda el restaurante?")
    assert r["route"] is None and "credencial" in r["reply"] and "metros" in r["reply"]


def test_each_category_only_guided_inside_its_zones():
    assert club_guide.answer("¿cómo llego al lounge?", "VIP")["route"]["destination"] == "lounge_vip"
    assert "no está incluido" in club_guide.answer("¿cómo llego al lounge?", "REGULAR")["reply"]
    assert "no está incluido" in club_guide.answer("¿dónde queda la cocina?", "INVITADO")["reply"]
    assert club_guide.answer("¿dónde queda la cocina?", "PERSONAL_INTERNO")["route"]["path"][-1] == "cocina"
    assert "no está incluido" in club_guide.answer("¿dónde está el restaurante?", "TRABAJADOR_EXTERNO")["reply"]


def test_spaces_listing_respects_category():
    vip = club_guide.answer("¿qué espacios tiene el club?", "VIP")["reply"]
    ext = club_guide.answer("¿qué espacios tiene el club?", "TRABAJADOR_EXTERNO")["reply"]
    assert "VIP Lounge" in vip and "canchas" in vip
    assert "Zona técnica" in ext and "Restaurante" not in ext


def test_robot_answers_directions_after_authorization(client, robot):
    decision, replies = session(client, robot, "QR-INV-001", ["¿cómo llego al restaurante?", "¿y la cocina?"])
    assert decision["decision"] == "AUTORIZADO"
    assert "Avance" in decision["speech"] or "avance" in decision["speech"]
    assert "anfitrión" in decision["speech"]
    assert replies[0]["intent"] == "UBICACION" and "metros" in replies[0]["speech"]
    assert "no está incluido" in replies[1]["speech"]


def test_five_category_closings(client, robot):
    from app.services.reception import CATEGORY_CLOSING

    categories = {c for c, _ in CATEGORY_CLOSING}
    assert categories == {"VIP", "REGULAR", "INVITADO", "PERSONAL_INTERNO", "TRABAJADOR_EXTERNO"}
    sid = client.post("/robot/sessions", json={"robot_id": "robot1"}, headers=robot).json()["id"]
    client.post(f"/robot/sessions/{sid}/faces", json={"persona_id": "EXT001", "similarity": 0.8}, headers=robot)
    client.post(f"/robot/sessions/{sid}/credentials", json={"payload": "QR-EXT-001"}, headers=robot)
    decision = client.post(f"/robot/sessions/{sid}/resolve", headers=robot).json()
    assert "acompañante" in decision["speech"] and "proveedores" in decision["speech"]


def test_gallery_manifest_changes_with_new_photo(client, robot, repo):
    first = client.get("/robot/gallery", headers=robot).json()
    assert set(first["personas"]) == {"VIP001", "INV001"}
    repo.upload_face("MEM-NEW", "admin-1.jpg", b"jpeg", "image/jpeg")
    client.app.state.ctx.reception.invalidate_gallery()
    second = client.get("/robot/gallery", headers=robot).json()
    assert second["version"] != first["version"] and second["personas"]["MEM-NEW"] == ["admin-1.jpg"]
    assert client.get("/robot/gallery").status_code == 401


def test_public_status_has_no_sensitive_data(client, robot):
    client.post("/robot/robot1/heartbeat", json={"camera_ok": True, "mic_ok": True, "name": "AGIBOT 01"},
                headers=robot)
    status = client.get("/robot/status").json()
    assert status["robots"][0]["connected"] is True
    assert set(status["robots"][0]) <= {"robot_id", "name", "connected", "camera_ok", "mic_ok", "mic_state",
                                        "simulated", "seconds_since_heartbeat"}


def test_cors_accepts_any_local_port(client):
    r = client.options("/robot/status", headers={"Origin": "http://localhost:5174",
                                                 "Access-Control-Request-Method": "GET"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5174"
    r = client.options("/robot/status", headers={"Origin": "https://malicioso.example",
                                                 "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in r.headers
