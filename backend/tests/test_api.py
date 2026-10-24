from urllib.parse import quote

import pytest


def session(client, robot, credential=None, face=None, text=None):
    sid = client.post("/robot/sessions", json={"robot_id": "x2-recepcion"}, headers=robot).json()["id"]
    if face:
        client.post(f"/robot/sessions/{sid}/faces", json=face, headers=robot)
    if text:
        client.post(f"/robot/sessions/{sid}/utterances", json={"text": text}, headers=robot)
    if credential:
        client.post(f"/robot/sessions/{sid}/credentials", json={"payload": credential}, headers=robot)
    return client.post(f"/robot/sessions/{sid}/resolve", headers=robot).json()


def face(pid, sim=0.8):
    return {"persona_id": pid, "similarity": sim}


# ---------- cinco flujos diferenciados ----------

def test_vip_face_and_credential_hands_off_to_robot2(client, robot):
    r = session(client, robot, "NFC-VIP-001", face("VIP001"))
    assert r["access"] == "authorized" and r["role"] == "VIP"
    assert r["robot_target"] == "robot2" and r["event_type"] == "vip_handoff"
    assert r["destination"] == "VIP Lounge"
    assert "facial" in r["methods"] and r["simulation"] is True
    assert r["route"]["path"][-1] == "lounge_vip" and "pasillo_vip" in r["route"]["path"]
    assert r["route"]["share_url"].startswith("http://app.test/#/ruta?t=")


def test_vip_without_face_goes_to_review(client, robot):
    r = session(client, robot, "NFC-VIP-001")
    assert r["access"] == "review" and r["decision"] == "REVISION"
    assert r["route"] is None


def test_regular_with_reservation(client, robot):
    r = session(client, robot, "APP-REG-001", text="Hola, tengo una reserva de golf")
    assert r["access"] == "authorized" and r["role"] == "REGULAR" and r["robot_target"] == "robot1"
    assert r["destination"] == "Campo de golf · Cancha 2"
    assert r["category_detected"] == "REGULAR"
    assert r["route"]["destination"] == "cancha_2"


def test_guest_invitation_host_and_destination(client, robot):
    r = session(client, robot, "QR-INV-001", text="Soy invitada de Valeria")
    assert r["access"] == "authorized" and r["role"] == "GUEST"
    assert r["destination"] == "Restaurante principal"
    assert {c["name"] for c in r["checks"]} >= {"invitación", "anfitrión"}
    assert all(n not in r["route"]["path"] for n in ("pasillo_vip", "corredor_personal"))


def test_staff_requires_face_and_gets_staff_corridor(client, robot):
    assert session(client, robot, "CAR-EMP-001")["access"] == "review"
    r = session(client, robot, "CAR-EMP-001", face("EMP001"))
    assert r["access"] == "authorized" and r["role"] == "STAFF"
    assert r["destination"] == "Oficina administrativa"


def test_provider_requires_escort_and_service_route(client, robot):
    r = session(client, robot, "QR-EXT-001", text="Vengo por una orden de mantenimiento")
    assert r["access"] == "pending" and r["decision"] == "ACOMPANAMIENTO" and r["escort_required"]
    path = r["route"]["path"]
    assert path[-1] == "zona_tecnica" and "recepcion_proveedores" in path
    assert not {"lobby", "galeria", "restaurante"} & set(path)
    assert any(s["action"] == "wait_escort" for s in r["route"]["steps"])


# ---------- casos dudosos y negativos ----------

def test_face_of_other_person_is_review(client, robot):
    r = session(client, robot, "APP-REG-001", face("VIP001"))
    assert r["access"] == "review"


def test_low_similarity_is_not_accepted(client, robot):
    r = session(client, robot, "NFC-VIP-001", face("VIP001", 0.5))
    assert r["access"] == "review"


def test_face_alone_never_authorizes(client, robot):
    r = session(client, robot, None, face("VIP001"))
    assert r["access"] == "review" and r["route"] is None


def test_unknown_and_demo_credentials_denied(client, robot):
    assert session(client, robot, "NO-EXISTE")["access"] == "denied"
    assert session(client, robot, "demo_abcdef")["access"] == "denied"


def test_revoked_invitation_and_suspended_membership(client, robot, repo):
    repo.update("invitaciones", "codigo_qr", "QR-INV-001", {"estado": "CANCELADA"})
    assert session(client, robot, "QR-INV-001")["access"] == "denied"
    repo.update("membresias", "persona_id", "REG001", {"estado": "SUSPENDIDA"})
    assert session(client, robot, "APP-REG-001")["access"] == "denied"


def test_guest_with_inactive_host_goes_to_review(client, robot, repo):
    repo.update("membresias", "persona_id", "VIP001", {"estado": "SUSPENDIDA"})
    assert session(client, robot, "QR-INV-001")["access"] == "review"


def test_secure_token_from_emitir_credencial(client, robot, repo):
    token = repo.issue_token("REG001", "MIEMBRO")
    r = session(client, robot, f"nclub:v1:{token}")
    assert r["access"] == "authorized" and "QR seguro" in r["methods"]
    repo.update("credenciales", "persona_id", "REG001", {"revocada_en": "2026-01-01T00:00:00+00:00"})
    assert session(client, robot, f"nclub:v1:{token}")["access"] == "denied"


def test_failed_persistence_never_authorizes(client, robot, repo):
    repo.fail_tables.add("eventos_acceso")
    r = session(client, robot, "APP-REG-001")
    assert r["access"] == "review" and "registrar" in r["reason"]


def test_resolve_is_idempotent(client, robot, repo):
    sid = client.post("/robot/sessions", json={"robot_id": "r"}, headers=robot).json()["id"]
    client.post(f"/robot/sessions/{sid}/credentials", json={"payload": "APP-REG-001"}, headers=robot)
    a = client.post(f"/robot/sessions/{sid}/resolve", headers=robot).json()
    b = client.post(f"/robot/sessions/{sid}/resolve", headers=robot).json()
    assert a == b and len(repo.tables["eventos_acceso"]) == 1


def test_records_session_identification_transcript_and_audit(client, robot, repo):
    session(client, robot, "NFC-VIP-001", face("VIP001"), "Buenos días, soy socia VIP")
    s = repo.tables["sesiones_atencion"][-1]
    assert s["decision"] == "AUTORIZADO" and s["categoria_confirmada"] == "VIP"
    assert s["credencial_enmascarada"] == "NFC-…"  # el código completo nunca se guarda
    assert {e["tipo"] for e in repo.tables["eventos_identificacion"]} == {"ROSTRO", "QR"}
    assert repo.tables["transcripciones"][-1]["intencion"] == "VIP"
    assert repo.tables["eventos_acceso"][-1]["simulacion"] is True
    assert repo.tables["auditoria"]
    assert any(event == "decision" for _, event, _ in repo.broadcasts)


# ---------- autenticación ----------

def test_robot_endpoints_require_key(client):
    assert client.post("/robot/sessions", json={"robot_id": "r"}).status_code == 401
    assert client.get("/rostros/VIP001", headers={"X-Robot-Key": "x" * 20}).status_code == 401


def test_monitor_requires_admin(client, robot, admin, repo):
    assert client.get("/robot/monitor").status_code == 401
    assert client.get("/robot/monitor", headers={"Authorization": "Bearer otro"}).status_code == 401
    repo.update("personas", "id", "REG001", {"auth_user_id": "socio"})
    repo.admin_token = "socio-token"
    repo.auth_user_id = lambda jwt: "socio" if jwt == "socio-token" else None
    assert client.get("/robot/monitor", headers={"Authorization": "Bearer socio-token"}).status_code == 403


def test_monitor_shows_live_state(client, robot, admin, repo):
    client.post("/robot/x2-recepcion/heartbeat", json={"camera_ok": True, "mic_ok": True, "mic_state": "escuchando"},
                headers=robot)
    jpeg = b"\xff\xd8\xff\xe0" + b"0" * 100
    assert client.put("/robot/x2-recepcion/frame", content=jpeg, headers=robot).status_code == 200
    session(client, robot, "QR-EXT-001", text="Vengo a mantenimiento")
    m = client.get("/robot/monitor", headers=admin).json()
    assert m["connected"] and m["microphone"]["state"] == "escuchando"
    assert m["camera_stream_url"].startswith("http://api.test/robot/stream/x2-recepcion.mjpeg?token=")
    assert m["last_heard"]["transcript"] == "Vengo a mantenimiento"
    assert m["events"][0]["decision"] == "ACOMPANAMIENTO"
    assert m["events"][0]["checks"]
    assert m["persistence"]["ok"]


def test_monitor_with_frames_before_first_heartbeat(client, robot, admin):
    client.put("/robot/r9/frame", content=b"\xff\xd8" + b"0" * 10, headers=robot)
    m = client.get("/robot/monitor", headers=admin)
    assert m.status_code == 200 and m.json()["connected"] is False
    assert m.json()["robot_name"] == "r9"


def test_stream_token_is_bound_to_robot(client, robot, admin):
    from app.deps import stream_token

    settings = client.app.state.ctx.settings
    assert client.get("/robot/stream/x2.mjpeg?token=a.1.b").status_code == 401
    token = stream_token(settings, "otro", "ADMIN001")
    assert client.get(f"/robot/stream/x2.mjpeg?token={token}").status_code == 401


# ---------- rostros: causa real de los 404 ----------

def test_rostros_with_spaces_and_parentheses(client, robot):
    names = client.get("/rostros/INV001", headers=robot).json()["fotografias"]
    assert names == ["WhatsApp Image 2026-10-24 at 00.23.06 (1).jpeg"]
    r = client.get(f"/rostros/INV001/{quote(names[0], safe='')}", headers=robot)
    assert r.status_code == 200 and r.content.endswith(names[0].encode())
    assert client.get("/rostros", headers=robot).json()["personas"] == ["INV001", "VIP001"]


@pytest.mark.parametrize("name,codes", [("noexiste.png", {404}), ("..%2Fsecreto.png", {400, 404}),
                                        (".oculto.png", {400}), ("foto1.txt", {400})])
def test_rostros_rejects_unknown_or_unsafe(client, robot, name, codes):
    assert client.get(f"/rostros/VIP001/{name}", headers=robot).status_code in codes


# ---------- contrato original y app web ----------

def test_legacy_resolve_access_contract(client, robot):
    r = client.post("/resolve-access", json={"face_group": "member", "credential_code": "NFC-VIP-001"},
                    headers=robot).json()
    assert r["role"] == "VIP" and r["access"] == "authorized" and r["destination"] == "VIP Lounge"
    r = client.post("/resolve-access", json={"face_group": "unknown", "credential_code": "NFC-VIP-001"},
                    headers=robot).json()
    assert r["access"] == "manual_review"
    r = client.post("/resolve-access", json={"face_group": "non_member", "credential_code": "QR-EXT-001"},
                    headers=robot).json()
    assert r["access"] == "pending_escort"


def test_frontend_validate_then_check_single_use(client, admin, repo):
    token = repo.issue_token("VIP001", "MIEMBRO")
    vid = client.post("/validate", json={"credential_token": token, "method": "qr"}, headers=admin).json()["validation_id"]
    r = client.post("/access/check", json={"validation_id": vid}, headers=admin)
    assert r.status_code == 200 and r.json()["role"] == "VIP"
    assert client.post("/access/check", json={"validation_id": vid}, headers=admin).status_code == 404


def test_frontend_simulation_contract(client, admin):
    r = client.post("/access/check", json={"visitor_id": "INV001", "scenario": "GUEST", "simulation": True,
                                           "requested_outcome": "authorized"}, headers=admin).json()
    assert r["simulation"] is True and r["role"] == "GUEST" and r["route"]["destination"] == "restaurante"
    r = client.post("/access/check", json={"visitor_id": "VIP001", "simulation": True,
                                           "requested_outcome": "denied"}, headers=admin).json()
    assert r["access"] == "denied" and r["robot_target"] == "robot1"


def test_shared_route_is_view_only_and_expires(client, robot):
    r = session(client, robot, "QR-INV-001")
    token = r["route"]["share_url"].split("t=")[1]
    shared = client.get(f"/navigation/shared/{token}").json()
    assert shared["route"]["destination"] == "restaurante"
    assert "visitor_id" not in str(shared) and "Camila" not in str(shared)
    assert client.get("/navigation/shared/" + "x" * 24).status_code == 404


def test_health_reports_simulation(client):
    assert client.get("/health").json() == {"status": "ok", "database": "memoria (simulación)", "simulation": True}
