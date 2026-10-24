"""Simulación MuJoCo de la clasificación en la recepción de N Club.

    python simulation/run_simulation.py                       # video build/nclub_clasificacion.mp4
    python simulation/run_simulation.py --viewer              # ventana interactiva de MuJoCo
    python simulation/run_simulation.py --solo vip,ext        # solo algunos flujos
    python simulation/run_simulation.py --backend http://127.0.0.1:8000 --robot-key <clave>
                                                              # en vivo: aparece en Admin → Robots

Sin --backend, el agente habla con un backend FastAPI en memoria dentro del
mismo proceso (datos demo, nunca Supabase). Todo es SIMULADO: no se usan
cámaras, micrófonos ni el robot físico.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

SIM = Path(__file__).resolve().parent
sys.path.insert(0, str(SIM))

from nclub_sim import voice as sim_voice  # noqa: E402
from nclub_sim.director import ROOT, SCENARIOS, Director, make_visitors  # noqa: E402

ROBOT_KEY_DEMO = "sim-mujoco-key-0123456789"


def memory_client(robot_id: str):
    """Backend real (create_app) en modo memoria, servido en el mismo proceso."""
    from fastapi.testclient import TestClient

    from app.config import Settings
    from app.main import create_app
    from app.memory_repo import MemoryRepository
    from nclub_agent.backend_client import BackendClient

    settings = Settings()
    settings.mode, settings.robot_api_key = "memory", ROBOT_KEY_DEMO
    repo = MemoryRepository(admin_token="sim-admin")
    # La base demo no trae voces grabadas: cada persona recibe su huella sintética.
    sim_voice.install(repo, [p["id"] for p in repo.tables["personas"]])
    test_client = TestClient(create_app(settings, repo))
    return BackendClient("http://testserver", ROBOT_KEY_DEMO, robot_id, client=test_client), repo


def face_engine():
    from nclub_vision.face import FaceEngine

    registry = ROOT / "vision" / "dataset" / "registro"
    if not registry.is_dir():
        print("Aviso: no está vision/dataset/registro; sin rostros, VIP y personal pasan a revisión.")
        return None
    engine = FaceEngine()
    engine.enroll_folder(registry)
    return engine


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--video", default=str(SIM / "build" / "nclub_clasificacion.mp4"), help="archivo MP4 de salida")
    parser.add_argument("--viewer", action="store_true", help="abre el visor interactivo de MuJoCo en vez de grabar")
    parser.add_argument("--solo", help="flujos separados por coma: " + ",".join(s[0] for s in SCENARIOS))
    parser.add_argument("--resolucion", default="1280x720", help="1280x720 o 1920x1080")
    parser.add_argument("--fps", type=int, default=24)
    parser.add_argument("--rapido", action="store_true", help="vista previa: 848x480 a 15 fps")
    parser.add_argument("--backend", help="URL del backend para modo en vivo (ej. http://127.0.0.1:8000)")
    parser.add_argument("--robot-key", default=os.environ.get("ROBOT_API_KEY"), help="X-Robot-Key del backend")
    parser.add_argument("--robot-id", default="robot-mujoco", help="id con el que aparece en Admin → Robots")
    parser.add_argument("--sin-rostros", action="store_true", help="no carga el reconocimiento facial")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(message)s")

    keys = [k.strip() for k in args.solo.split(",")] if args.solo else None
    visitors = make_visitors(keys)
    if not [v for v in visitors if v.key != "esc"]:
        sys.exit("Ningún flujo coincide con --solo")

    heartbeat = None
    if args.backend:
        from nclub_agent.backend_client import BackendClient

        if not args.robot_key:
            sys.exit("Modo en vivo: indique --robot-key (o la variable ROBOT_API_KEY) del backend")
        client = BackendClient(args.backend, args.robot_key, args.robot_id)

        def heartbeat(status: dict) -> None:
            try:
                client.heartbeat(**status, name=args.robot_id, model="AGIBOT X2 Ultra (simulado en MuJoCo)",
                                 camera_topic="mujoco:r1_head_cam", audio_topic="texto simulado")
            except Exception as error:  # el video sigue aunque el backend no responda
                print("Latido no enviado:", error)
        print(f"Modo en vivo contra {args.backend} como '{args.robot_id}' (sesiones marcadas como simuladas)")
    else:
        client, _ = memory_client(args.robot_id)

    engine = None if args.sin_rostros else face_engine()
    if args.rapido:
        args.resolucion, args.fps = "848x480", 15
    width, height = (int(v) for v in args.resolucion.lower().split("x"))
    print("Construyendo la escena…")
    director = Director(client, engine, visitors, fps=args.fps, live=bool(args.backend), heartbeat=heartbeat)
    if args.viewer:
        run_viewer(director)
    else:
        record(director, Path(args.video), width, height)


def record(director: Director, out: Path, width: int, height: int) -> None:
    import imageio.v2 as imageio
    import mujoco

    from nclub_sim.hud import Hud

    out.parent.mkdir(parents=True, exist_ok=True)
    renderer = mujoco.Renderer(director.model, height, width)
    hud = Hud(width, height, director.info.club)
    writer = imageio.get_writer(str(out), fps=director.fps, codec="libx264", quality=8, macro_block_size=8)
    started, frames, decisions = time.time(), 0, []
    try:
        for st in director.run():
            renderer.update_scene(director.data, camera=director.camera)
            writer.append_data(hud.compose(renderer.render(), st))
            frames += 1
            if st.decision and (not decisions or decisions[-1][0] != st.visitor.key):
                decisions.append((st.visitor.key, st.visitor.name, st.decision.get("decision"),
                                  st.decision.get("destination")))
            if frames % (director.fps * 5) == 0:
                print(f"\r  {frames / director.fps:5.0f} s de video · {time.time() - started:5.0f} s reales", end="", flush=True)
    finally:
        writer.close()
    print(f"\nVideo: {out} ({frames / director.fps:.0f} s)")
    for key, name, decision, destination in decisions:
        print(f"  {name:24s} → {decision:15s} {destination or ''}")


def run_viewer(director: Director) -> None:
    import mujoco.viewer

    with mujoco.viewer.launch_passive(director.model, director.data) as viewer:
        viewer.cam.type = mujoco.mjtCamera.mjCAMERA_FREE
        for st in director.run():
            if not viewer.is_running():
                break
            tick = time.time()
            viewer.cam.lookat[:] = director.camera.lookat
            viewer.cam.distance = director.camera.distance
            viewer.cam.azimuth, viewer.cam.elevation = director.camera.azimuth, director.camera.elevation
            if hasattr(viewer, "set_texts"):  # MuJoCo >= 3.2
                viewer.set_texts((mujoco.mjtFontScale.mjFONTSCALE_150, mujoco.mjtGridPos.mjGRID_TOPLEFT,
                                  "N Club - SIMULACION", _viewer_text(st)))
            viewer.sync()
            time.sleep(max(0.0, director.dt - (time.time() - tick)))


def _viewer_text(st) -> str:
    parts = []
    if st.visitor:
        parts.append(f"{st.flow_index}/{st.flow_total} {st.visitor.name}")
    if st.decision:
        parts.append(f"{st.decision.get('decision')} → {st.decision.get('destination') or ''}")
    if st.subtitles:
        parts.append(f"{st.subtitles[-1].speaker}: {st.subtitles[-1].text[:70]}")
    return "\n".join(parts) or " "


if __name__ == "__main__":
    main()
