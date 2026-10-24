import base64
from urllib.parse import quote

import pytest
from conftest import REG_VOICE, VIP_VOICE


def session(client, robot, credential=None, face=None, text=None, voice=None):
    """text puede ser una frase o una lista; voice acompaña cada frase como audio del locutor."""
    sid = client.post("/robot/sessions", json={"robot_id": "x2-recepcion"}, headers=robot).json()["id"]
    if face:
        client.post(f"/robot/sessions/{sid}/faces", json=face, headers=robot)
    for phrase in ([text] if isinstance(text, str) else text or []):
        body = {"text": phrase}
        if voice is not None:
            body["speaker_audio_wav_b64"] = base64.b64encode(voice).decode()
        client.post(f"/robot/sessions/{sid}/utterances", json=body, headers=robot)
    if credential:
        client.post(f"/robot/sessions/{sid}/credentials", json={"payload": credential}, headers=robot)
    return client.post(f"/robot/sessions/{sid}/resolve", headers=robot).json()


def face(pid, sim=0.8):
    return {"persona_id": pid, "similarity": sim}


def regular(client, robot, credential=None, digits="4567", voice=REG_VOICE):
    """Socio regular: rostro + nombre completo y últimos cuatro dígitos del documento (con su voz) + actividad."""
    return session(client, robot, credential, face("REG001"),
                   [f"Soy Santiago Ruiz, termina en {digits}", "Tengo una reserva de golf"], voice=voice)


# ---------- cinco flujos diferenciados ----------

def test_vip_face_and_voice_hands_off_to_robot2(client, robot):
    r = session(client, robot, None, face("VIP001"), "Quiero ir al VIP Lounge", voice=VIP_VOICE)
    assert r["access"] == "authorized" and r["role"] == "VIP"
    assert r["robot_target"] == "robot2" and r["event_type"] == "vip_handoff"
    assert r["destination"] == "VIP Lounge"
    assert "facial" in r["methods"] and r["simulation"] is True
    checks = {c["name"]: c["ok"] for c in r["checks"]}
    assert checks["rostro"] and checks["voz"] and "credencial" not in checks  # VIP: sin credencial
    assert r["route"]["path"][-1] == "lounge_vip" and "pasillo_vip" in r["route"]["path"]
    assert r["route"]["share_url"].startswith("http://app.test/#/ruta?t=")


def test_vip_utterance_with_matching_voice_triggers_decision(client, robot):
    sid = client.post("/robot/sessions", json={"robot_id": "r"}, headers=robot).json()["id"]
    greeting = client.post(f"/robot/sessions/{sid}/faces", json=face("VIP001"), headers=robot).json()
    assert "VIP" in greeting["speech"]
    reply = client.post(f"/robot/sessions/{sid}/utterances", headers=robot, json={
        "text": "Quiero ir al lounge", "speaker_audio_wav_b64": base64.b64encode(VIP_VOICE).decode()}).json()
    assert reply["ready"] is True


def test_vip_with_other_voice_goes_to_review(client, robot):
    r = session(client, robot, None, face("VIP001"), ["Quiero ir al lounge", "Al lounge, por favor"], voice=b"otra voz")
    assert r["access"] == "review" and any(c["name"] == "voz" and not c["ok"] for c in r["checks"])


def test_vip_credential_does_not_replace_voice(client, robot):
    assert session(client, robot, "NFC-VIP-001", face("VIP001"))["access"] == "review"


def test_vip_without_face_goes_to_review(client, robot):
    r = session(client, robot, "NFC-VIP-001")
    assert r["access"] == "review" and r["decision"] == "REVISION"
    assert r["route"] is None


def test_regular_with_reservation(client, robot):
    r = regular(client, robot)
    assert r["access"] == "authorized" and r["role"] == "REGULAR" and r["robot_target"] == "robot1"
    checks = {c["name"]: c["ok"] for c in r["checks"]}
    assert checks["pregunta de identidad"] and checks["voz"] and "credencial" not in checks
    assert r["destination"] == "Campo de golf · Cancha 2"
    assert r["category_detected"] == "REGULAR"
    assert r["route"]["destination"] == "cancha_2"


def test_regular_wrong_document_digits_goes_to_review(client, robot):
    r = session(client, robot, None, face("REG001"), ["Santiago Ruiz 1111", "Santiago Ruiz 2222",
                                                      "Santiago Ruiz 3333"], voice=REG_VOICE)
    assert r["access"] == "review"
    assert any(c["name"] == "pregunta de identidad" and not c["ok"] for c in r["checks"])


def test_regular_is_strict_and_asks_for_what_is_missing(client, robot):
    sid = client.post("/robot/sessions", json={"robot_id": "r"}, headers=robot).json()["id"]
    greeting = client.post(f"/robot/sessions/{sid}/faces", json=face("REG001"), headers=robot).json()["speech"]
    assert "nombre completo" in greeting and "cuatro dígitos" in greeting
    say = lambda text, voice=REG_VOICE: client.post(f"/robot/sessions/{sid}/utterances", headers=robot, json={  # noqa: E731
        "text": text, "speaker_audio_wav_b64": base64.b64encode(voice).decode()}).json()
    assert "cuatro dígitos" in say("Me llamo Santiago Ruiz")["speech"]
    assert "voz" in say("Termina en 4567", b"otra voz")["speech"]  # datos correctos, voz ajena
    assert say("Termina en 4567")["intent"] == "IDENTIDAD_CONFIRMADA"


def test_regular_without_voice_is_not_authorized(client, robot):
    r = regular(client, robot, voice=b"otra voz")
    assert r["access"] == "review"


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
    assert any(c["name"] == "horario de trabajo" and c["ok"] and "turno" in c["detail"] for c in r["checks"])


def test_staff_outside_shift_is_denied(client, robot, repo):
    repo.update("permisos_laborales", "codigo_autorizacion", "CAR-EMP-001",
                {"valido_desde": "2020-01-01T08:00:00+00:00", "valido_hasta": "2020-01-01T17:00:00+00:00"})
    r = session(client, robot, "CAR-EMP-001", face("EMP001"))
    assert r["access"] == "denied" and r["reason"] == "Fuera del horario de trabajo"


def test_provider_requires_escort_and_service_route(client, robot):
    assert session(client, robot, "QR-EXT-001")["access"] == "review"  # rostro + QR de la orden
    r = session(client, robot, "QR-EXT-001", face("EXT001"), "Vengo por una orden de mantenimiento")
    assert r["access"] == "pending" and r["decision"] == "ACOMPANAMIENTO" and r["escort_required"]
    assert any(c["name"] == "orden de trabajo" and c["ok"] for c in r["checks"])
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
    assert regular(client, robot)["access"] == "denied"


def test_guest_with_inactive_host_goes_to_review(client, robot, repo):
    repo.update("membresias", "persona_id", "VIP001", {"estado": "SUSPENDIDA"})
    assert session(client, robot, "QR-INV-001")["access"] == "review"


def test_secure_token_from_emitir_credencial(client, robot, repo):
    token = repo.issue_token("EMP001", "PERSONAL")
    r = session(client, robot, f"nclub:v1:{token}", face("EMP001"))
    assert r["access"] == "authorized" and "QR seguro" in r["methods"]
    repo.update("credenciales", "persona_id", "EMP001", {"revocada_en": "2026-01-01T00:00:00+00:00"})
    assert session(client, robot, f"nclub:v1:{token}")["access"] == "denied"


def test_failed_persistence_never_authorizes(client, robot, repo):
    repo.fail_tables.add("eventos_acceso")
    r = regular(client, robot)
    assert r["access"] == "review" and "registrar" in r["reason"]


def test_resolve_is_idempotent(client, robot, repo):
    sid = client.post("/robot/sessions", json={"robot_id": "r"}, headers=robot).json()["id"]
    client.post(f"/robot/sessions/{sid}/credentials", json={"payload": "APP-REG-001"}, headers=robot)
    a = client.post(f"/robot/sessions/{sid}/resolve", headers=robot).json()
    b = client.post(f"/robot/sessions/{sid}/resolve", headers=robot).json()
    assert a == b and len(repo.tables["eventos_acceso"]) == 1


def test_records_session_identification_transcript_and_audit(client, robot, repo):
    session(client, robot, "QR-INV-001", None, "Soy invitada de Valeria")
    assert repo.tables["sesiones_atencion"][-1]["credencial_enmascarada"] not in (None, "QR-INV-001")  # nunca el código completo
    session(client, robot, None, face("VIP001"), "Quiero ir al VIP Lounge", voice=VIP_VOICE)
    s = repo.tables["sesiones_atencion"][-1]
    assert s["decision"] == "AUTORIZADO" and s["categoria_confirmada"] == "VIP"
    assert {e["tipo"] for e in repo.tables["eventos_identificacion"]} == {"ROSTRO", "QR", "VOZ"}
    assert repo.tables["transcripciones"][-1]["intencion"] == "ACTIVIDAD_SOLICITADA"
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
    session(client, robot, "QR-EXT-001", face("EXT001"), text="Vengo a mantenimiento")
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
    # El contrato heredado no trae voz ni pregunta de identidad: los socios pasan a recepción.
    r = client.post("/resolve-access", json={"face_group": "member", "credential_code": "NFC-VIP-001"},
                    headers=robot).json()
    assert r["role"] == "VIP" and r["access"] == "manual_review"
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
