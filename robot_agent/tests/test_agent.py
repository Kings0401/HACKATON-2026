"""Pruebas con hardware simulado: el agente real contra el backend real (memoria)."""

import sys
from pathlib import Path

import httpx
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT / "robot_agent", ROOT / "vision", ROOT / "backend"):
    sys.path.insert(0, str(p))

from fastapi.testclient import TestClient  # noqa: E402

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402
from app.memory_repo import MemoryRepository  # noqa: E402
from nclub_agent import sim  # noqa: E402
from nclub_agent.backend_client import BackendClient, BackendUnavailable  # noqa: E402
from nclub_agent.core import OFFLINE_MESSAGE, AgentConfig, LogSpeaker, ReceptionAgent  # noqa: E402
from nclub_agent.speech import pcm_to_wav  # noqa: E402
from nclub_agent.speech import VAD_BEGIN, VAD_END, VAD_PROCESSING, AimdkVadAssembler, EnergyVAD  # noqa: E402
from nclub_vision.qr import QrReader, encode_qr  # noqa: E402

KEY = "sim-robot-key-0123456789"
HAS_DATASET = (ROOT / "vision" / "dataset" / "registro").is_dir() and (
    ROOT / "vision" / "models" / "face_recognition_sface_2021dec.onnx").is_file()


VIP_PCM = b"\x10\x00" * 16000  # voz de Valeria para el locutor simulado
REG_PCM = b"\x20\x00" * 16000  # voz de Santiago


@pytest.fixture
def backend(monkeypatch):
    from app.services import speaker_id

    monkeypatch.setattr(speaker_id, "verify_many", lambda refs, spoken, threshold=0.25: {
        "similarity": 0.9 if spoken in refs else 0.1, "matched": spoken in refs, "matches": int(spoken in refs),
        "samples": len(refs), "threshold": threshold, "model": "prueba"})
    s = Settings()
    s.mode, s.robot_api_key = "memory", KEY
    repo = MemoryRepository(admin_token="adm")
    repo.upload_voice("VIP001", "enrollment.wav", pcm_to_wav(VIP_PCM), "audio/wav")
    repo.upload_voice("REG001", "enrollment.wav", pcm_to_wav(REG_PCM), "audio/wav")
    return TestClient(create_app(s, repo)), repo


def client_for(test_client):
    return BackendClient("http://testserver", KEY, "robot-sim", client=test_client)


@pytest.mark.skipif(not HAS_DATASET, reason="requiere vision/dataset y modelos ONNX locales")
def test_five_flows_end_to_end_with_faces(backend):
    tc, repo = backend
    results = {r["scenario"]: r for r in sim.run("", KEY, client=client_for(tc), voices={"VIP001": VIP_PCM, "REG001": REG_PCM})}
    assert results["VIP"]["decision"] == "AUTORIZADO" and results["VIP"]["robot_target"] == "robot2"
    checks = {k: {c["name"] for c in r["checks"] if c["ok"]} for k, r in results.items()}
    assert "voz" in checks["VIP"] and {"pregunta de identidad", "voz"} <= checks["REGULAR"]
    assert "horario de trabajo" in checks["PERSONAL"] and "orden de trabajo" in checks["PROVEEDOR"]
    assert results["REGULAR"]["decision"] == "AUTORIZADO" and results["REGULAR"]["destination"].startswith("Campo")
    assert results["INVITADO"]["decision"] == "AUTORIZADO" and results["INVITADO"]["destination"] == "Restaurante principal"
    assert results["PERSONAL"]["decision"] == "AUTORIZADO"
    assert results["PROVEEDOR"]["decision"] == "ACOMPANAMIENTO"
    assert len({r["route"]["destination"] for r in results.values()}) == 5  # cinco rutas distintas
    assert all("facial" in r["methods"] for r in results.values())
    sessions = repo.tables["sesiones_atencion"]
    assert len(sessions) == 5 and all(s["estado"] == "CERRADA" for s in sessions)
    assert len(repo.tables["transcripciones"]) == 6  # el regular responde dos veces


def test_flows_without_faces_send_doubtful_cases_to_review(backend):
    tc, _ = backend
    results = {r["scenario"]: r for r in sim.run("", KEY, with_faces=False, client=client_for(tc))}
    # Todas las categorías salvo el invitado combinan rostro con su factor: sin rostro nadie más entra.
    assert results["INVITADO"]["decision"] == "AUTORIZADO"
    for flow in ("VIP", "REGULAR", "PERSONAL", "PROVEEDOR"):
        assert results[flow]["decision"] in ("REVISION", "DENEGADO"), flow
    assert results["PERSONAL"]["decision"] == "REVISION" and results["PROVEEDOR"]["decision"] == "REVISION"


def test_agent_speaks_offline_message_when_backend_is_down():
    def refuse(request):
        raise httpx.ConnectError("sin red", request=request)

    client = BackendClient("http://robot.invalid", KEY, "r", transport=httpx.MockTransport(refuse))
    speaker = LogSpeaker()
    agent = ReceptionAgent(client, None, QrReader(), speaker, config=AgentConfig(analyze_every_s=0))
    assert agent.on_frame(encode_qr("APP-REG-001")) is None
    assert speaker.spoken == [OFFLINE_MESSAGE] and client.online is False


def test_client_reconnects_after_transient_failures():
    calls = {"n": 0}

    def flaky(request):
        calls["n"] += 1
        if calls["n"] < 3:
            raise httpx.ConnectError("caída", request=request)
        return httpx.Response(200, json={"ok": True})

    client = BackendClient("http://robot.test", KEY, "r", transport=httpx.MockTransport(flaky))
    states = []
    client.on_status(states.append)
    assert client.request("GET", "/health", retries=2) == {"ok": True}
    assert client.online and states == [True]
    with pytest.raises(BackendUnavailable):
        BackendClient("http://robot.test", KEY, "r",
                      transport=httpx.MockTransport(lambda r: httpx.Response(503))).request("GET", "/", retries=1)


def test_aimdk_vad_assembler_joins_fragments():
    vad = AimdkVadAssembler()
    chunk = b"\x01\x00" * 4000
    assert vad.feed(VAD_BEGIN, chunk) is None
    assert vad.feed(VAD_PROCESSING, chunk) is None
    utterance = vad.feed(VAD_END, chunk)
    assert utterance == chunk * 3


def test_energy_vad_detects_speech_between_silence():
    rate = 16000
    silence = np.zeros(rate, dtype=np.int16)
    tone = (np.sin(np.arange(rate) * 2 * np.pi * 220 / rate) * 8000).astype(np.int16)
    audio = np.concatenate([silence, tone, silence]).tobytes()
    vad = EnergyVAD()
    utterances = [u for i in range(0, len(audio), 3200) for u in vad.feed(audio[i:i + 3200])]
    assert len(utterances) == 1
    assert 0.9 < len(utterances[0]) / 2 / rate < 1.8


def test_same_qr_is_not_resolved_twice_while_visible(backend):
    tc, repo = backend
    t = [0.0]
    agent = ReceptionAgent(client_for(tc), None, QrReader(), LogSpeaker(),
                           config=AgentConfig(analyze_every_s=0), clock=lambda: t[0])
    qr = encode_qr("QR-INV-001")
    assert agent.on_frame(qr)["decision"] == "AUTORIZADO"
    t[0] += 1
    assert agent.on_frame(qr) is None
    assert len(repo.tables["eventos_acceso"]) == 1


def test_face_tracker_needs_consensus_and_ignores_single_glitch():
    from types import SimpleNamespace as M

    from nclub_agent.core import FaceTracker

    tracker = FaceTracker()
    vip, other, unknown = (M(persona_id="VIP001", score=0.8), M(persona_id="REG001", score=0.7),
                           M(persona_id=None, score=0.3))
    assert tracker.add(vip, 0.0) is None          # un solo fotograma no basta
    assert tracker.add(other, 0.2) is None        # fotograma erróneo aislado
    assert tracker.add(vip, 0.4).persona_id == "VIP001"
    fresh = FaceTracker()
    for t in (0.0, 0.2):
        assert fresh.add(unknown, t) is None
    assert fresh.add(unknown, 0.4).persona_id is None  # tres sin coincidencia: desconocido
    stale = FaceTracker()
    stale.add(vip, 0.0)
    assert stale.add(vip, 5.0) is None            # votos viejos caducan
