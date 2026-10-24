"""Director de escena: recorre los flujos de clasificación con el agente REAL.

Cada visitante llega a la recepción, el AGIBOT 01 lo mira con la cámara de la
frente (render de MuJoCo), el ReceptionAgent del robot analiza esos fotogramas
con YuNet/SFace y el lector QR, recibe la frase del visitante y el backend
(AccessEngine + navegación Dijkstra) decide. La decisión no se guiona: lo que
se ve en el video es lo que respondió el backend.
"""

from __future__ import annotations

import math
import re
import sys
from dataclasses import dataclass, field
from typing import Callable, Iterator

import mujoco
import numpy as np

from . import voice as sim_voice
from .animation import Rig, hide_person, look_at, present_qr_pose, robot_pose, set_person, stand_pose, walk_pose
from .scene import ROOT, SceneInfo, Visitor, build, face_texture, to_world

for _p in (ROOT / "robot_agent", ROOT / "vision", ROOT / "backend"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from nclub_agent.core import AgentConfig, ReceptionAgent  # noqa: E402
from nclub_vision.qr import QrReader  # noqa: E402

WALK_SPEED = 1.3  # m/s, paso tranquilo
HEAD_CAM = (720, 1280)  # resolución a la que el robot analiza (como la cámara real)
FACE_DIST = 0.85  # distancia de conversación frente al robot
ROUTE_SECONDS = 13.0  # duración en video del recorrido (se acelera si la ruta es larga)

# Personas de la base demo (backend/app/memory_repo.py) y sus frases.
SCENARIOS = [
    ("vip", "VIP001", "Valeria Torres", "VIP", "NFC-VIP-001", "Quiero descansar en el VIP Lounge, por favor.", (0.86, 0.70, 0.58), 1.66),
    ("reg", "REG001", "Santiago Ruiz", "REGULAR", "APP-REG-001", "Tengo una reserva de golf.", (0.78, 0.60, 0.48), 1.78),
    ("inv", "INV001", "Camila López", "INVITADO", "QR-INV-001", "Gracias. Vengo invitada por Valeria Torres.", (0.84, 0.66, 0.54), 1.64),
    ("emp", "EMP001", "Daniel Moreno", "PERSONAL_INTERNO", "CAR-EMP-001", "¡Muy bien, gracias! Aquí tiene mi carné.", (0.70, 0.52, 0.40), 1.75),
    ("ext", "EXT001", "Laura Pérez", "TRABAJADOR_EXTERNO", "QR-EXT-001", "Claro, aquí está la orden de servicio.", (0.82, 0.64, 0.50), 1.68),
    ("unk", None, "Visitante sin registro", "DESCONOCIDO", "QR-NO-REGISTRADO-77", "Hola, quiero entrar al club.", (0.76, 0.58, 0.46), 1.72),
]
FLOW_TITLES = {
    "VIP": "Socio VIP", "REGULAR": "Socio regular", "INVITADO": "Invitado",
    "PERSONAL_INTERNO": "Personal interno", "TRABAJADOR_EXTERNO": "Proveedor / trabajador externo",
    "DESCONOCIDO": "Persona no registrada",
}
STAGES = ("Rostro", "Diálogo", "Credencial", "Decisión", "Ruta")
# Diferencial de cada categoría: el tercer paso es su segundo factor junto al rostro.
FLOW_STAGES = {
    "VIP": ("Rostro", "Saludo", "Voz", "Decisión", "Ruta"),
    "REGULAR": ("Rostro", "Saludo", "Identidad", "Decisión", "Ruta"),  # nombre + documento + voz
    "INVITADO": ("Rostro", "Diálogo", "QR invit.", "Decisión", "Ruta"),
    "PERSONAL_INTERNO": ("Rostro", "Diálogo", "Carné", "Decisión", "Ruta"),  # + horario del turno
    "TRABAJADOR_EXTERNO": ("Rostro", "Diálogo", "QR orden", "Decisión", "Ruta"),
}
FACE_FIRST = ("VIP", "REGULAR")  # se deciden sin credencial
# Documento del socio regular en la base demo (backend/app/memory_repo.py): el robot le pide su
# nombre completo y los últimos cuatro dígitos.
DOCUMENTS = {"REG001": "1020304567"}


def make_visitors(keys: list[str] | None = None) -> list[Visitor]:
    out = []
    for key, pid, name, cat, cred, phrase, skin, height in SCENARIOS:
        if keys and key not in keys:
            continue
        out.append(Visitor(key, pid, name, cat, cred, phrase, face_texture(pid) if pid else None, skin, height))
    if any(v.category == "TRABAJADOR_EXTERNO" for v in out):
        out.append(Visitor("esc", None, "Acompañante", "PERSONAL_INTERNO", "", "", None, (0.74, 0.56, 0.44), 1.80))
    return out


def split_sentences(text: str) -> list[str]:
    parts = [p.strip() for p in re.split(r"(?<=[.!?;])\s+", text or "") if p.strip()]
    return parts or ([text] if text else [])


@dataclass
class Subtitle:
    speaker: str
    text: str
    until: float


@dataclass
class Shot:
    """Cámara libre interpolada suavemente hacia un objetivo."""
    lookat: np.ndarray
    distance: float
    azimuth: float
    elevation: float


class SimSpeaker:
    """Voz del robot simulado: encola frases para los subtítulos (sin audio)."""

    def __init__(self, director: "Director", who: str = "AGIBOT 01"):
        self.director, self.who = director, who

    def speak(self, text: str) -> None:
        self.director.say(self.who, text)


@dataclass
class FrameState:
    """Lo que el HUD necesita saber del instante actual."""
    t: float = 0.0
    flow_index: int = 0
    flow_total: int = 0
    visitor: Visitor | None = None
    stage: int = -1
    stages: tuple = STAGES
    decision: dict | None = None
    headcam: np.ndarray | None = None
    matches: list = field(default_factory=list)
    readings: list = field(default_factory=list)
    subtitles: list[Subtitle] = field(default_factory=list)
    banner: str | None = None
    timelapse: float = 1.0
    route_progress: float = 0.0
    position: tuple[float, float] | None = None
    note: str | None = None


class Director:
    def __init__(self, client, face_engine, visitors: list[Visitor], fps: int = 30,
                 live: bool = False, heartbeat: Callable[[dict], None] | None = None):
        self.model, self.info = build(visitors)
        self.data = mujoco.MjData(self.model)
        self.rig = Rig(self.model)
        self.fps, self.dt = fps, 1.0 / fps
        self.visitors = [v for v in visitors if v.key != "esc"]
        self.escort = next((v for v in visitors if v.key == "esc"), None)
        self.state = FrameState(flow_total=len(self.visitors))
        self.speech: list[tuple[str, str]] = []  # cola (quién, frase)
        self.speech_free_at = 0.0
        self.heartbeat = heartbeat
        self.last_heartbeat = -1e9
        # La voz sintética solo la reconoce el backend en memoria (nclub_sim.voice).
        self.send_voice = not live
        self.head_renderer = mujoco.Renderer(self.model, *HEAD_CAM)
        from nclub_vision.sources import encode_jpeg

        self.agent = ReceptionAgent(
            client, face_engine, QrReader(), SimSpeaker(self),
            config=AgentConfig(simulated=True, analyze_every_s=0, upload_every_s=0.4 if live else 1e9),
            encode_jpeg=encode_jpeg if live else None, clock=lambda: self.state.t,
        )
        self.agent.on_session_start = lambda: setattr(self, "r1_wave_at", self.state.t)
        self.r1_wave_at = -99.0
        self.r2_wave_at = -99.0
        self.r1_target: np.ndarray | None = None
        self.r2_target: np.ndarray | None = None
        self.positions: dict[str, tuple[tuple[float, float], float, dict]] = {}
        rx, ry = self.info.robot1_xy
        self.shot = Shot(np.array([rx, ry - 2.0, 1.0]), 6.5, 115.0, -14.0)
        self.goal = Shot(self.shot.lookat.copy(), self.shot.distance, self.shot.azimuth, self.shot.elevation)
        self.camera = mujoco.MjvCamera()
        self.camera.type = mujoco.mjtCamera.mjCAMERA_FREE
        self.route_geoms: list[int] = []
        for v in visitors:
            hide_person(self.data, self.rig, v.key)

    # ---------------- voz y subtítulos ----------------

    def say(self, who: str, text: str) -> None:
        # Una respuesta nueva reemplaza lo que ese hablante aún no alcanzó a decir.
        self.speech = [(w, t) for w, t in self.speech if w != who]
        for sentence in split_sentences(text):
            self.speech.append((who, sentence))

    def _update_subtitles(self) -> None:
        t = self.state.t
        self.state.subtitles = [s for s in self.state.subtitles if s.until > t]
        if self.speech and t >= self.speech_free_at:
            who, text = self.speech.pop(0)
            duration = 1.2 + len(text) * 0.055  # lectura cómoda en pantalla
            self.state.subtitles = [s for s in self.state.subtitles if s.speaker != who][-1:]
            self.state.subtitles.append(Subtitle(who, text, t + duration))
            self.speech_free_at = t + duration

    def robot_quiet(self) -> bool:
        return not self.speech and self.state.t >= self.speech_free_at

    def visitor_says(self, visitor: Visitor, text: str) -> None:
        self.state.subtitles = [s for s in self.state.subtitles if s.speaker == "AGIBOT 01"][-1:]
        self.state.subtitles.append(Subtitle(visitor.name, text, self.state.t + 2.8))

    # ---------------- cámara ----------------

    def aim(self, lookat, distance, azimuth, elevation) -> None:
        self.goal = Shot(np.asarray(lookat, float), distance, azimuth, elevation)

    def _update_camera(self, rate: float = 2.2) -> None:
        k = 1 - math.exp(-rate * self.dt)
        s, g = self.shot, self.goal
        s.lookat += (g.lookat - s.lookat) * k
        s.distance += (g.distance - s.distance) * k
        s.azimuth += ((g.azimuth - s.azimuth + 180) % 360 - 180) * k
        s.elevation += (g.elevation - s.elevation) * k
        self.camera.lookat[:] = s.lookat
        self.camera.distance, self.camera.azimuth, self.camera.elevation = s.distance, s.azimuth, s.elevation

    # ---------------- un fotograma ----------------

    def _frame(self) -> FrameState:
        st = self.state
        info = self.info
        hy, hp = (look_at(info.robot1_xy, info.robot1_yaw, self.r1_target) if self.r1_target is not None else (0.0, 0.0))
        w1 = st.t - self.r1_wave_at
        robot_pose(self.data, self.rig, "r1_", info.robot1_xy, info.robot1_yaw, head_yaw=hy, head_pitch=hp,
                   wave=w1 if 0 <= w1 <= 3 else None, t=st.t)
        hy2, hp2 = (look_at(info.robot2_xy, info.robot2_yaw, self.r2_target) if self.r2_target is not None else (0.0, 0.0))
        w2 = st.t - self.r2_wave_at
        robot_pose(self.data, self.rig, "r2_", info.robot2_xy, info.robot2_yaw, head_yaw=hy2, head_pitch=hp2,
                   wave=w2 if 0 <= w2 <= 3 else None, t=st.t + 1.3)
        for key, (xy, yaw, pose) in self.positions.items():
            set_person(self.data, self.rig, key, xy, yaw, pose)
        mujoco.mj_forward(self.model, self.data)
        self._update_subtitles()
        self._update_camera()
        if self.heartbeat and st.t - self.last_heartbeat >= 5:
            self.last_heartbeat = st.t
            self.heartbeat(self.agent.status())
        st.t += self.dt
        return st

    def headcam(self) -> np.ndarray:
        self.head_renderer.update_scene(self.data, camera="r1_head_cam")
        self.head_renderer.scene.flags[mujoco.mjtRndFlag.mjRND_SHADOW] = 0  # no cambia el análisis
        return self.head_renderer.render()[:, :, ::-1].copy()

    def _look(self, analyze: bool) -> dict | None:
        """Renderiza la cámara de la frente y (opcional) la pasa al agente."""
        frame = self.headcam()
        self.state.headcam = frame
        if not analyze:
            return None
        decision = self.agent.on_frame(frame)
        self.state.matches, self.state.readings = list(self.agent.last_matches), list(self.agent.last_readings)
        return decision

    # ---------------- ayudantes de guion ----------------

    def hold(self, seconds: float, update: Callable[[float], None] | None = None, look_every: float = 0.0,
             analyze: bool = False, until: Callable[[], bool] | None = None) -> Iterator[FrameState]:
        n = max(1, int(round(seconds * self.fps)))
        step = max(1, int(round(look_every * self.fps))) if look_every else 0
        for i in range(n):
            if update:
                update(i / n)
            if step and i % step == 0:
                mujoco.mj_forward(self.model, self.data)
                self._look(analyze)
            yield self._frame()
            if until and until():
                return

    def face_point(self, visitor: Visitor) -> np.ndarray:
        xy, _, _ = self.positions[visitor.key]
        return np.array([xy[0], xy[1], 1.60 * visitor.height / 1.70])

    def walk(self, key: str, path: list[tuple[float, float]], speed: float, video_seconds: float | None = None,
             on_step: Callable[[tuple[float, float], float], None] | None = None,
             companion: str | None = None) -> Iterator[FrameState]:
        """Camina por una polilínea. Si video_seconds se da, acelera el tiempo."""
        pts = [np.asarray(p, float) for p in path]
        lengths = [float(np.linalg.norm(b - a)) for a, b in zip(pts, pts[1:])]
        total = sum(lengths) or 1e-6
        real = total / speed
        span = video_seconds or real
        self.state.timelapse = max(1.0, real / span)
        n = max(1, int(span * self.fps))
        for i in range(n + 1):
            d = total * i / n
            seg, acc = 0, 0.0
            while seg < len(lengths) - 1 and acc + lengths[seg] < d:
                acc += lengths[seg]
                seg += 1
            a, b = pts[seg], pts[seg + 1]
            u = 0.0 if lengths[seg] == 0 else (d - acc) / lengths[seg]
            pos = a + (b - a) * min(1.0, u)
            yaw = math.atan2(b[1] - a[1], b[0] - a[0])
            gait = walk_pose(self.state.t * 2 * math.pi * 0.95) if i < n else stand_pose()
            self.positions[key] = ((pos[0], pos[1]), yaw, gait)
            if companion:
                side = np.array([-math.sin(yaw), math.cos(yaw)]) * 0.9
                self.positions[companion] = ((pos[0] + side[0], pos[1] + side[1]), yaw,
                                             walk_pose(self.state.t * 2 * math.pi * 0.95 + 1.2) if i < n else stand_pose())
            self.state.position = (pos[0], pos[1])
            self.state.route_progress = d / total
            if on_step:
                on_step((pos[0], pos[1]), yaw)
            yield self._frame()
        self.state.timelapse = 1.0

    def _route_world(self, decision: dict) -> list[tuple[float, float]]:
        route = decision.get("route") or {}
        return [to_world(self.info.club, x, y) for x, y in route.get("points", [])]

    def _show_route(self, decision: dict, visible: bool) -> None:
        for gid in self.route_geoms:
            self.model.geom_rgba[gid, 3] = 0.0
        self.route_geoms = []
        if not visible:
            return
        path = (decision.get("route") or {}).get("path", [])
        rgb = {"VIP": (0.75, 0.58, 0.24), "REGULAR": (0.10, 0.55, 0.36), "INVITADO": (0.16, 0.48, 0.78),
               "PERSONAL_INTERNO": (0.48, 0.34, 0.82), "TRABAJADOR_EXTERNO": (0.86, 0.45, 0.10)}.get(
            decision.get("category"), (0.2, 0.5, 0.8))
        for a, b in zip(path, path[1:]):
            for name in (f"route_{a}_{b}", f"route_{b}_{a}"):
                gid = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_GEOM, name)
                if gid >= 0:
                    self.model.geom_rgba[gid] = [*rgb, 0.92]
                    self.route_geoms.append(gid)

    # ---------------- guion completo ----------------

    def run(self) -> Iterator[FrameState]:
        rx, ry = self.info.robot1_xy
        yield from self.intro()
        for index, visitor in enumerate(self.visitors):
            self.state = FrameState(t=self.state.t, flow_index=index + 1, flow_total=len(self.visitors), visitor=visitor,
                                    subtitles=self.state.subtitles, stages=FLOW_STAGES.get(visitor.category, STAGES))
            yield from self.flow(visitor, rx, ry)
        yield from self.outro()

    def intro(self) -> Iterator[FrameState]:
        rx, ry = self.info.robot1_xy
        self.state.banner = "N Club · Recepción con AGIBOT X2 Ultra"
        self.shot = Shot(np.array([rx, ry - 30, 2.0]), 70.0, 100.0, -32.0)
        self.aim([rx, ry - 1.0, 1.0], 6.5, 115.0, -14.0)
        yield from self.hold(4.0)
        self.state.banner = None

    def outro(self) -> Iterator[FrameState]:
        rx, ry = self.info.robot1_xy
        self.state.visitor, self.state.decision, self.state.stage = None, None, -1
        self.state.banner = "Fin de la simulación · 5 categorías + persona no registrada"
        self.aim([rx, ry + 60, 0.0], 180.0, 100.0, -58.0)
        yield from self.hold(4.5)

    def flow(self, v: Visitor, rx: float, ry: float) -> Iterator[FrameState]:
        st = self.state
        st.banner = f"Flujo {st.flow_index} de {st.flow_total} · {FLOW_TITLES[v.category]}"
        stop = (rx, ry - FACE_DIST)
        start = (rx + 2.5, ry - 9.0)
        self.positions[v.key] = (start, math.pi / 2, stand_pose())
        self.r1_target = None
        self.aim([rx + 0.6, ry - 3.0, 1.0], 7.5, 125.0, -12.0)

        # 1) Llega a la recepción. El robot la sigue con la mirada desde ~4 m.
        def approach(pos, _yaw):
            if math.dist(pos, self.info.robot1_xy) < 4.5:
                self.r1_target = self.face_point(v)
        yield from self.walk(v.key, [start, (rx + 0.8, ry - 3.0), stop], WALK_SPEED, on_step=approach)
        self.positions[v.key] = (stop, math.pi / 2, stand_pose())
        self.r1_target = self.face_point(v)
        st.banner = None

        # 2) Rostro: la cámara de la frente analiza varios fotogramas (votación 2 de 3).
        st.stage = 0
        self.aim([rx, ry - 0.55, 1.25], 3.2, 150.0, -8.0)
        yield from self.hold(2.4, look_every=0.25, analyze=True)

        # 3) Diálogo: el visitante responde a lo que pregunta el robot. VIP y
        #    regular confirman aquí su identidad (voz / últimos dígitos del documento).
        st.stage = 1
        face_first = v.category in FACE_FIRST
        voice = self.send_voice and face_first
        replies = ([f"Soy {v.name}, mi documento termina en {DOCUMENTS[v.persona_id][-4:]}."]
                   if v.persona_id in DOCUMENTS else [])
        for take, text in enumerate([*replies, v.phrase], start=1):
            yield from self.hold(14.0, look_every=0.25, analyze=True, until=self.robot_quiet)
            if face_first:
                st.stage = 2
                st.note = "Voz simulada: huella sintética, sin audio real" if voice else None
            self.visitor_says(v, text)
            audio = sim_voice.utterance_pcm(v.persona_id, take) if voice else None
            self.agent.on_text(text, 0.92, "simulado", speaker_audio=audio)
            yield from self.hold(2.6, look_every=0.25, analyze=True)
            if self.agent.state.decision:
                break
        st.note = None

        # 4) Credencial (invitado, personal y proveedor): muestra el QR a la cámara.
        st.stage = 2
        raised = not face_first and self.agent.state.decision is None
        if raised:
            self.aim([rx + 0.1, ry - 0.6, 1.25], 2.6, 160.0, -6.0)

        def raise_phone(k):
            # Gira un poco el torso para dejar el teléfono frente a la cámara.
            xy, _, _ = self.positions[v.key]
            u = min(1.0, k * 2.2)
            self.positions[v.key] = (xy, math.pi / 2 + 0.42 * u * u * (3 - 2 * u), present_qr_pose(u))
            # El robot baja la mirada hacia el teléfono a medida que lo levanta.
            qr = self.data.geom_xpos[self.model.geom(f"v_{v.key}_qr").id]
            face = self.face_point(v)
            self.r1_target = face + (np.asarray(qr) - face) * u
        if raised:
            yield from self.hold(4.5, raise_phone, look_every=0.2, analyze=True,
                                 until=lambda: self.agent.state.decision is not None)
        decision = self.agent.state.decision
        if decision is None:  # sin QR legible: el backend decide con lo que tiene
            decision = self.agent._resolve() if self.agent.state.session_id else None
        st.decision = decision
        st.stage = 3

        # 5) Decisión: el robot la comunica; si es VIP avisa al AGIBOT 02.
        self.aim([rx, ry - 0.8, 1.15], 4.2, 135.0, -10.0)

        self.r1_target = self.face_point(v)

        def lower(k):
            xy, _, _ = self.positions[v.key]
            u = max(0.0, 1 - k * 1.5)
            self.positions[v.key] = (xy, math.pi / 2 + 0.42 * u, present_qr_pose(u))
        if raised:
            yield from self.hold(1.0, lower)
        yield from self.hold(4.0, look_every=0.5, analyze=False)

        if not decision or not decision.get("route") or decision.get("decision") not in ("AUTORIZADO", "ACOMPANAMIENTO"):
            yield from self.not_admitted(v, rx, ry, decision)
        else:
            yield from self.route(v, decision)
        hide_person(self.data, self.rig, v.key)
        self.positions.pop(v.key, None)
        if self.escort:
            self.positions.pop(self.escort.key, None)
            hide_person(self.data, self.rig, self.escort.key)
        self._show_route(decision or {}, False)
        self.r1_target = self.r2_target = None
        # El visitante ya no está frente al robot: el agente cierra la sesión.
        self.state.t += 3.0
        self.agent.tick()
        self.speech.clear()
        self.speech_free_at = self.state.t

    def not_admitted(self, v: Visitor, rx: float, ry: float, decision: dict | None) -> Iterator[FrameState]:
        self.state.note = "Derivado a recepción humana: el robot no autoriza el ingreso"
        yield from self.hold(3.0)
        self.r1_target = None
        self.aim([rx, ry - 4.0, 1.0], 8.0, 110.0, -14.0)
        back = [(rx, ry - FACE_DIST), (rx - 1.5, ry - 3.0), (rx - 3.0, ry - 9.0)]
        yield from self.walk(v.key, back, WALK_SPEED)
        self.state.note = None

    def route(self, v: Visitor, decision: dict) -> Iterator[FrameState]:
        st = self.state
        st.stage = 4
        pts = self._route_world(decision)
        if len(pts) < 2:
            return
        self._show_route(decision, True)
        rx, ry = self.info.robot1_xy
        pts[0] = (rx, ry - FACE_DIST)
        route = decision["route"]
        escort_at = None
        if decision.get("decision") == "ACOMPANAMIENTO" and route.get("escort_point"):
            node = route["escort_point"]
            if node in route["path"]:
                escort_at = route["path"].index(node)
        # Vista aérea que sigue al visitante; al pasar junto al AGIBOT 02 (VIP), traspaso.
        vip = decision.get("robot_target") == "robot2"
        handed = [False]
        self.r1_target = None

        def follow(pos, yaw):
            far = math.dist(pos, self.info.robot1_xy)
            self.aim([pos[0], pos[1], 0.8], min(38.0, 7 + far * 0.35), math.degrees(yaw) + 200, -38.0)
        segments = [pts] if escort_at is None else [pts[:escort_at + 1], pts[escort_at:]]
        total = sum(math.dist(a, b) for a, b in zip(pts, pts[1:])) or 1.0
        for si, seg in enumerate(segments):
            share = sum(math.dist(a, b) for a, b in zip(seg, seg[1:])) / total
            if vip and si == 0:
                yield from self._walk_with_handoff(v, seg, share, follow, handed)
            else:
                yield from self.walk(v.key, seg, WALK_SPEED, ROUTE_SECONDS * max(share, 0.25), follow,
                                     companion=self.escort.key if (self.escort and si == 1) else None)
            if escort_at is not None and si == 0:
                yield from self._escort_meets(v, seg[-1])
        st.note = f"Llegó a {route.get('destination_label', 'su destino')}"
        end = pts[-1]
        self.aim([end[0], end[1], 1.0], 9.0, self.shot.azimuth + 30, -20.0)
        yield from self.hold(2.0)
        st.note = None

    def _walk_with_handoff(self, v, seg, share, follow, handed):
        vx, vy = self.info.robot2_xy
        cut = min(range(len(seg)), key=lambda i: math.dist(seg[i], (vx, vy)))
        spot = (vx, vy - 1.0)  # frente al AGIBOT 02 (mira al sur)
        first, second = [*seg[:cut + 1], spot], [spot, *seg[cut:]]
        if len(first) >= 2:
            yield from self.walk(v.key, first, WALK_SPEED, ROUTE_SECONDS * share * 0.6, follow)
        # Traspaso VIP: el AGIBOT 02 recibe a la socia (saludo y mirada).
        self.state.note = "Traspaso VIP: AGIBOT 02 recibe a la socia"
        self.r2_target = self.face_point(v)
        self.r2_wave_at = self.state.t
        xy, _, _ = self.positions[v.key]
        self.positions[v.key] = (xy, math.pi / 2, stand_pose())
        self.say("AGIBOT 02", f"Bienvenida, {v.name.split()[0]}. La acompaño al VIP Lounge.")
        self.aim([(xy[0] + vx) / 2, (xy[1] + vy) / 2, 1.1], 4.2, -25.0, -9.0)
        yield from self.hold(3.5)
        self.state.note = None
        self.r2_target = None
        if len(second) >= 2:
            yield from self.walk(v.key, second, WALK_SPEED, ROUTE_SECONDS * share * 0.4, follow)

    def _escort_meets(self, v, point):
        self.state.note = "Espera a su acompañante en la recepción de proveedores"
        xy, yaw, _ = self.positions[v.key]
        self.positions[v.key] = (xy, yaw, stand_pose())
        self.aim([point[0], point[1], 1.0], 9.0, self.shot.azimuth, -22.0)
        yield from self.hold(1.5)
        if self.escort:
            far = (point[0] + 7.0, point[1] + 4.0)
            near = (point[0] + 0.9, point[1] + 0.3)
            yield from self.walk(self.escort.key, [far, near], WALK_SPEED)
            self.say("Acompañante", f"Hola, {v.name.split()[0]}. La acompaño a la zona técnica.")
            yield from self.hold(2.0)
        self.state.note = None
