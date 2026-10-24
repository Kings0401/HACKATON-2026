"""La simulación usa el agente y el backend reales: verifica las decisiones
que salen del render (sin grabar video). Requiere el modelo descargado."""

import sys
from pathlib import Path

import pytest

SIM = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SIM))

from nclub_sim.scene import MODEL  # noqa: E402

ROOT = SIM.parent
HAS_FACES = (ROOT / "vision" / "dataset" / "registro").is_dir() and (
    ROOT / "vision" / "models" / "face_recognition_sface_2021dec.onnx").is_file()
pytestmark = pytest.mark.skipif(not MODEL.is_file(), reason="python simulation/download_model.py")


def run_flows(keys, faces=True):
    import run_simulation
    from nclub_sim.director import Director, make_visitors

    client, repo = run_simulation.memory_client("robot-mujoco-test")
    engine = run_simulation.face_engine() if faces else None
    director = Director(client, engine, make_visitors(keys), fps=10)
    decisions = {}
    for st in director.run():
        if st.decision and st.visitor:
            decisions[st.visitor.key] = st.decision
    return decisions, repo


@pytest.mark.skipif(not HAS_FACES, reason="requiere vision/dataset y modelos ONNX")
def test_vip_recognized_from_head_camera_and_handed_to_robot2():
    decisions, repo = run_flows(["vip"])
    vip = decisions["vip"]
    assert vip["decision"] == "AUTORIZADO" and vip["robot_target"] == "robot2"
    assert "facial" in vip["methods"]
    ok = {c["name"] for c in vip["checks"] if c["ok"]}
    assert "voz" in ok and "credencial" not in ok  # VIP: rostro + voz, sin credencial
    assert all(s["estado"] == "CERRADA" for s in repo.tables["sesiones_atencion"])


@pytest.mark.skipif(not HAS_FACES, reason="requiere vision/dataset y modelos ONNX")
def test_each_category_uses_its_own_factor():
    decisions, _ = run_flows(["reg", "inv", "emp", "ext"])
    ok = {k: {c["name"] for c in d["checks"] if c["ok"]} for k, d in decisions.items()}
    assert decisions["reg"]["decision"] == "AUTORIZADO" and "pregunta de identidad" in ok["reg"]
    assert "credencial" not in ok["reg"] and "voz" in ok["reg"]  # regular: nombre, documento y voz
    assert decisions["inv"]["decision"] == "AUTORIZADO" and {"invitación", "anfitrión"} <= ok["inv"]
    assert decisions["emp"]["decision"] == "AUTORIZADO" and "horario de trabajo" in ok["emp"]
    assert decisions["ext"]["decision"] == "ACOMPANAMIENTO" and "orden de trabajo" in ok["ext"]
    assert decisions["ext"]["route"]["escort_point"]


def test_unknown_is_not_admitted():
    decisions, _ = run_flows(["unk"], faces=False)
    assert decisions["unk"]["decision"] not in ("AUTORIZADO", "ACOMPANAMIENTO")
