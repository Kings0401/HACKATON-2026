"""Escena MuJoCo de N Club: el club (desde shared/club-map.json), dos AGIBOT X2
Ultra oficiales y los visitantes de las cinco categorías.

Coordenadas: 1 unidad del mapa = 0.6 m (escala real del mapa); el origen es la
recepción y +Y apunta al norte del plano.
"""

from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import mujoco
import numpy as np

SIM = Path(__file__).resolve().parents[1]
ROOT = SIM.parent
MODEL_FULL = SIM / "models" / "x2_ultra" / "x2_ultra.xml"
# Misma cinemática con mallas visuales simplificadas (render ~6x más rápido).
MODEL_LITE = SIM / "models" / "x2_ultra" / "x2_ultra_lite.xml"
MODEL = MODEL_LITE if MODEL_LITE.is_file() else MODEL_FULL
CLUB_MAP = ROOT / "shared" / "club-map.json"
DATASET = ROOT / "vision" / "dataset"
BUILD = SIM / "build"

ROBOT_BASE_Z = 0.68  # altura de la pelvis en el modelo oficial (pies sobre el suelo)
ZONE_RGB = {  # tonos del sistema de diseño claro
    "PUBLICA": (0.85, 0.83, 0.76), "SOCIOS": (0.62, 0.70, 0.86), "CAMPO": (0.45, 0.66, 0.42),
    "VIP": (0.83, 0.72, 0.48), "PERSONAL": (0.86, 0.66, 0.40), "SERVICIO": (0.82, 0.50, 0.44),
    "TECNICA": (0.78, 0.50, 0.66),
}
CATEGORY_RGB = {
    "VIP": (0.66, 0.53, 0.29), "REGULAR": (0.12, 0.54, 0.37), "INVITADO": (0.18, 0.47, 0.72),
    "PERSONAL_INTERNO": (0.48, 0.36, 0.78), "TRABAJADOR_EXTERNO": (0.76, 0.42, 0.12), "DESCONOCIDO": (0.45, 0.45, 0.48),
}


@dataclass
class Visitor:
    key: str
    persona_id: str | None
    name: str
    category: str
    credential: str
    phrase: str
    face_image: Path | None = None
    skin: tuple = (0.80, 0.64, 0.52)
    height: float = 1.70


@dataclass
class SceneInfo:
    club: dict
    scale: float
    nodes_xy: dict[str, tuple[float, float]]
    robot1_xy: tuple[float, float]
    robot1_yaw: float
    robot2_xy: tuple[float, float]
    robot2_yaw: float
    visitors: list[Visitor] = field(default_factory=list)
    edge_index: dict[tuple[str, str], int] = field(default_factory=dict)


def load_club() -> dict:
    return json.loads(CLUB_MAP.read_text(encoding="utf-8"))


def to_world(club: dict, x: float, y: float) -> tuple[float, float]:
    start = club["nodes"][club["start"]]
    s = club["units"]["scale_m_per_unit"]
    return (x - start["x"]) * s, -(y - start["y"]) * s


def yaw_quat(yaw: float) -> list[float]:
    return [math.cos(yaw / 2), 0.0, 0.0, math.sin(yaw / 2)]


def face_texture(persona_id: str) -> Path | None:
    """Recorte del rostro de prueba (dataset/pruebas) para la cara del visitante."""
    folder = DATASET / "pruebas" / persona_id
    files = sorted(folder.glob("foto3.*")) or sorted(folder.glob("*.png")) if folder.is_dir() else []
    if not files:
        return None
    image = cv2.imread(str(files[0]))
    try:
        from nclub_vision.face import FaceEngine

        faces = FaceEngine().detect(image)
    except Exception:
        faces = []
    if len(faces):
        x, y, w, h = (int(v) for v in faces[0][:4])
        cx, cy, side = x + w / 2, y + h / 2, int(max(w, h) * 1.45)
        x0, y0 = int(max(0, cx - side / 2)), int(max(0, cy - side / 2))
        image = image[y0:y0 + side, x0:x0 + side]
    image = cv2.resize(image, (512, 512), interpolation=cv2.INTER_CUBIC)
    out = BUILD / "textures" / f"face_{persona_id}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), image)
    return out


def qr_texture(key: str, payload: str) -> Path:
    from nclub_vision.qr import encode_qr

    out = BUILD / "textures" / f"qr_{key}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), cv2.resize(encode_qr(payload, 300), (256, 256), interpolation=cv2.INTER_NEAREST))
    return out


def _texture(spec, name: str, path: Path, emission: float = 0.0) -> str:
    spec.add_texture(name=f"tex_{name}", type=mujoco.mjtTexture.mjTEXTURE_2D, file=str(path))
    spec.add_material(name=f"mat_{name}", textures=["", f"tex_{name}"], emission=emission,
                      specular=0.0, shininess=0.0)
    return f"mat_{name}"


def _box(body, name, pos, size, rgba, **kw):
    return body.add_geom(name=name, type=mujoco.mjtGeom.mjGEOM_BOX, pos=pos, size=size, rgba=rgba,
                         contype=0, conaffinity=0, **kw)


def _segment(body, name, a, b, width, z, height, rgba):
    (x0, y0), (x1, y1) = a, b
    length = math.hypot(x1 - x0, y1 - y0)
    yaw = math.atan2(y1 - y0, x1 - x0)
    return _box(body, name, [(x0 + x1) / 2, (y0 + y1) / 2, z], [length / 2 + width / 2, width / 2, height],
                list(rgba), quat=yaw_quat(yaw))


def _person(spec, visitor: Visitor, start_xy):
    """Visitante articulado: raíz mocap + caderas, rodillas, hombros y codos."""
    rgb = CATEGORY_RGB[visitor.category]
    shirt, pants, skin = [*rgb, 1], [0.18, 0.2, 0.24, 1], [*visitor.skin, 1]
    root = spec.worldbody.add_body(name=f"v_{visitor.key}", mocap=True, pos=[*start_xy, 0])
    h = visitor.height / 1.70
    hip_z, sh_z, head_z = 0.92 * h, 1.42 * h, 1.60 * h
    root.add_geom(name=f"v_{visitor.key}_torso", type=mujoco.mjtGeom.mjGEOM_CAPSULE, fromto=[0, 0, hip_z + 0.06, 0, 0, sh_z - 0.04],
                  size=[0.16 * h, 0, 0], rgba=shirt, contype=0, conaffinity=0)
    root.add_geom(name=f"v_{visitor.key}_hips", type=mujoco.mjtGeom.mjGEOM_ELLIPSOID, pos=[0, 0, hip_z],
                  size=[0.13 * h, 0.17 * h, 0.09 * h], rgba=pants, contype=0, conaffinity=0)
    root.add_geom(name=f"v_{visitor.key}_neck", type=mujoco.mjtGeom.mjGEOM_CAPSULE, fromto=[0, 0, sh_z, 0, 0, head_z - 0.08],
                  size=[0.05 * h, 0, 0], rgba=skin, contype=0, conaffinity=0)
    head = root.add_body(name=f"v_{visitor.key}_head", pos=[0, 0, head_z])
    head.add_geom(name=f"v_{visitor.key}_skull", type=mujoco.mjtGeom.mjGEOM_ELLIPSOID, size=[0.10 * h, 0.085 * h, 0.12 * h],
                  rgba=skin, contype=0, conaffinity=0)
    head.add_geom(name=f"v_{visitor.key}_hair", type=mujoco.mjtGeom.mjGEOM_ELLIPSOID, pos=[-0.02, 0, 0.04 * h],
                  size=[0.105 * h, 0.09 * h, 0.1 * h], rgba=[0.16, 0.12, 0.1, 1], contype=0, conaffinity=0)
    if visitor.face_image:
        mat = _texture(spec, f"face_{visitor.key}", visitor.face_image, emission=0.55)
        # Plano con la foto del rostro: es lo que "ve" la cámara de la frente del robot.
        head.add_geom(name=f"v_{visitor.key}_face", type=mujoco.mjtGeom.mjGEOM_BOX, pos=[0.098 * h, 0, -0.01],
                      size=[0.003, 0.12 * h, 0.12 * h], material=mat, contype=0, conaffinity=0)
    for side, sy in (("l", 1), ("r", -1)):
        leg = root.add_body(name=f"v_{visitor.key}_hip_{side}", pos=[0, 0.09 * h * sy, hip_z - 0.02])
        leg.add_joint(name=f"v_{visitor.key}_hipj_{side}", type=mujoco.mjtJoint.mjJNT_HINGE, axis=[0, 1, 0])
        leg.add_geom(name=f"v_{visitor.key}_thigh_{side}", type=mujoco.mjtGeom.mjGEOM_CAPSULE, fromto=[0, 0, 0, 0, 0, -0.42 * h],
                     size=[0.065 * h, 0, 0], rgba=pants, contype=0, conaffinity=0)
        knee = leg.add_body(name=f"v_{visitor.key}_knee_{side}", pos=[0, 0, -0.43 * h])
        knee.add_joint(name=f"v_{visitor.key}_kneej_{side}", type=mujoco.mjtJoint.mjJNT_HINGE, axis=[0, 1, 0])
        knee.add_geom(name=f"v_{visitor.key}_shin_{side}", type=mujoco.mjtGeom.mjGEOM_CAPSULE, fromto=[0, 0, 0, 0, 0, -0.40 * h],
                      size=[0.05 * h, 0, 0], rgba=pants, contype=0, conaffinity=0)
        knee.add_geom(name=f"v_{visitor.key}_shoe_{side}", type=mujoco.mjtGeom.mjGEOM_BOX, pos=[0.05, 0, -0.43 * h],
                      size=[0.12 * h, 0.05 * h, 0.035], rgba=[0.1, 0.1, 0.1, 1], contype=0, conaffinity=0)
        arm = root.add_body(name=f"v_{visitor.key}_sh_{side}", pos=[0, 0.2 * h * sy, sh_z - 0.03])
        arm.add_joint(name=f"v_{visitor.key}_shj_{side}", type=mujoco.mjtJoint.mjJNT_HINGE, axis=[0, 1, 0])
        arm.add_geom(name=f"v_{visitor.key}_upper_{side}", type=mujoco.mjtGeom.mjGEOM_CAPSULE, fromto=[0, 0, 0, 0, 0, -0.30 * h],
                     size=[0.05 * h, 0, 0], rgba=shirt, contype=0, conaffinity=0)
        elbow = arm.add_body(name=f"v_{visitor.key}_el_{side}", pos=[0, 0, -0.31 * h])
        elbow.add_joint(name=f"v_{visitor.key}_elj_{side}", type=mujoco.mjtJoint.mjJNT_HINGE, axis=[0, 1, 0])
        elbow.add_geom(name=f"v_{visitor.key}_fore_{side}", type=mujoco.mjtGeom.mjGEOM_CAPSULE, fromto=[0, 0, 0, 0, 0, -0.27 * h],
                       size=[0.042 * h, 0, 0], rgba=skin, contype=0, conaffinity=0)
        if side == "r":
            # Teléfono con la credencial QR (sale de la mano derecha).
            mat = _texture(spec, f"qr_{visitor.key}", qr_texture(visitor.key, visitor.credential), emission=0.8)
            # Pantalla perpendicular al antebrazo: con el brazo al frente queda de cara al robot.
            hand = elbow.add_body(name=f"v_{visitor.key}_phone_body", pos=[0.0, 0, -0.32 * h])
            hand.add_geom(name=f"v_{visitor.key}_phone", type=mujoco.mjtGeom.mjGEOM_BOX, pos=[0.075, 0, 0],
                          size=[0.09, 0.05, 0.006], rgba=[0.08, 0.08, 0.1, 1], contype=0, conaffinity=0)
            hand.add_geom(name=f"v_{visitor.key}_qr", type=mujoco.mjtGeom.mjGEOM_BOX, pos=[0.08, 0, -0.0075],
                          size=[0.046, 0.046, 0.0015], material=mat, contype=0, conaffinity=0)
    return root


def build(visitors: list[Visitor]) -> tuple[mujoco.MjModel, SceneInfo]:
    if not MODEL.is_file():
        raise SystemExit("Falta el modelo del robot: python simulation/download_model.py")
    club = load_club()
    s = club["units"]["scale_m_per_unit"]
    nodes_xy = {k: to_world(club, n["x"], n["y"]) for k, n in club["nodes"].items()}
    spec = mujoco.MjSpec()
    spec.modelname = "nclub_recepcion"
    spec.option.timestep = 0.002
    vis = spec.visual
    vis.global_.offwidth, vis.global_.offheight = 1920, 1080
    vis.quality.shadowsize = 8192
    # El club mide ~600 m: se fija la escala visual en la recepción para que la
    # cámara dibuje desde 8 cm (robot y rostros) hasta ~1 km (horizonte).
    spec.stat.extent = 40.0
    spec.stat.center = [0, 0, 1]
    vis.map.znear = 0.002
    vis.map.zfar = 25.0
    vis.map.shadowclip = 0.5  # sombras nítidas en ~20 m alrededor de la acción
    vis.headlight.ambient = [0.35, 0.35, 0.35]
    vis.headlight.diffuse = [0.45, 0.45, 0.45]
    vis.headlight.specular = [0.1, 0.1, 0.1]
    spec.add_texture(name="sky", type=mujoco.mjtTexture.mjTEXTURE_SKYBOX, builtin=mujoco.mjtBuiltin.mjBUILTIN_GRADIENT,
                     rgb1=[0.62, 0.78, 0.93], rgb2=[0.96, 0.97, 0.98], width=512, height=3072)
    spec.add_texture(name="grass", type=mujoco.mjtTexture.mjTEXTURE_2D, builtin=mujoco.mjtBuiltin.mjBUILTIN_CHECKER,
                     rgb1=[0.34, 0.53, 0.30], rgb2=[0.32, 0.50, 0.28], width=512, height=512)
    spec.add_material(name="grass", textures=["", "grass"], texrepeat=[400, 400], reflectance=0.0)
    world = spec.worldbody
    world.add_light(name="sun", type=mujoco.mjtLightType.mjLIGHT_DIRECTIONAL, pos=[0, 0, 60], dir=[-0.35, 0.45, -1], diffuse=[0.75, 0.73, 0.68],
                    specular=[0.2, 0.2, 0.2], castshadow=True)
    world.add_geom(name="ground", type=mujoco.mjtGeom.mjGEOM_PLANE, size=[400, 400, 0.1], material="grass", pos=[0, 80, 0])

    # Zonas del plano (losas tenues) y caminos.
    for i, area in enumerate(club["areas"]):
        x, y, w, hgt = area["rect"]
        (x0, y0), (x1, y1) = to_world(club, x, y), to_world(club, x + w, y + hgt)
        _box(world, f"zone_{area['id']}", [(x0 + x1) / 2, (y0 + y1) / 2, 0.004 + i * 0.001],
             [abs(x1 - x0) / 2, abs(y1 - y0) / 2, 0.004], [*ZONE_RGB[area["zone"]], 0.35])
    edge_index = {}
    for i, (a, b) in enumerate(club["edges"]):
        _segment(world, f"path_{a}_{b}", nodes_xy[a], nodes_xy[b], 2.4, 0.02, 0.012, (0.86, 0.84, 0.78, 1))
        # Cinta de la ruta (invisible hasta que el robot la asigna).
        _segment(world, f"route_{a}_{b}", nodes_xy[a], nodes_xy[b], 1.1, 0.045, 0.01, (0.1, 0.5, 0.35, 0))
        edge_index[(a, b)] = edge_index[(b, a)] = i

    # Hitos: un poste por lugar, con el color de su zona; fuente en el lobby; lago.
    for key, node in club["nodes"].items():
        x, y = nodes_xy[key]
        rgb = ZONE_RGB[node["zone"]]
        if key == "lobby":
            world.add_geom(name="fountain", type=mujoco.mjtGeom.mjGEOM_CYLINDER, pos=[x + 4, y, 0.25], size=[2.2, 0.25, 0],
                           rgba=[0.78, 0.76, 0.72, 1], contype=0, conaffinity=0)
            world.add_geom(name="fountain_water", type=mujoco.mjtGeom.mjGEOM_CYLINDER, pos=[x + 4, y, 0.46], size=[1.9, 0.03, 0],
                           rgba=[0.35, 0.6, 0.75, 0.9], contype=0, conaffinity=0)
        if node["kind"] in ("destination", "hub", "entrance"):
            world.add_geom(name=f"post_{key}", type=mujoco.mjtGeom.mjGEOM_CYLINDER, pos=[x + 1.8, y + 1.8, 0.9],
                           size=[0.12, 0.9, 0], rgba=[0.3, 0.3, 0.32, 1], contype=0, conaffinity=0)
            world.add_geom(name=f"sign_{key}", type=mujoco.mjtGeom.mjGEOM_BOX, pos=[x + 1.8, y + 1.8, 1.95],
                           size=[0.5, 0.06, 0.28], rgba=[*rgb, 1], contype=0, conaffinity=0)
    lx, ly = to_world(club, 300, 300)
    world.add_geom(name="lake", type=mujoco.mjtGeom.mjGEOM_ELLIPSOID, pos=[lx, ly, -0.6], size=[26, 18, 0.7],
                   rgba=[0.32, 0.55, 0.68, 1], contype=0, conaffinity=0)

    # Árboles deterministas en el campo y alrededor de la casa club.
    rng = random.Random(7)
    for i in range(90):
        x, y = rng.uniform(-260, 280), rng.uniform(-30, 330)
        if any(math.hypot(x - nx, y - ny) < 9 for nx, ny in nodes_xy.values()):
            continue
        if any(_near_segment((x, y), nodes_xy[a], nodes_xy[b], 5) for a, b in club["edges"]):
            continue
        hgt = rng.uniform(5, 9)
        world.add_geom(name=f"trunk_{i}", type=mujoco.mjtGeom.mjGEOM_CYLINDER, pos=[x, y, hgt * 0.3], size=[0.25, hgt * 0.3, 0],
                       rgba=[0.42, 0.31, 0.22, 1], contype=0, conaffinity=0)
        world.add_geom(name=f"crown_{i}", type=mujoco.mjtGeom.mjGEOM_ELLIPSOID, pos=[x, y, hgt * 0.75],
                       size=[hgt * 0.32, hgt * 0.32, hgt * 0.38], rgba=[0.24 + rng.uniform(-0.04, 0.04), 0.45, 0.24, 1],
                       contype=0, conaffinity=0)

    # Pabellón de recepción con pérgola (sin techo sólido: se ve desde arriba).
    rx, ry = nodes_xy[club["start"]]
    _box(world, "reception_floor", [rx, ry + 1, 0.01], [7, 6, 0.01], [0.80, 0.77, 0.71, 1])
    for cx in (-6.5, 6.5):
        for cy in (-4.5, 6.5):
            world.add_geom(name=f"column_{cx}_{cy}", type=mujoco.mjtGeom.mjGEOM_CYLINDER, pos=[rx + cx, ry + cy, 1.7],
                           size=[0.18, 1.7, 0], rgba=[0.95, 0.95, 0.93, 1], contype=0, conaffinity=0)
    for i in range(9):
        _box(world, f"pergola_{i}", [rx - 6 + i * 1.5, ry + 1, 3.45], [0.06, 6.2, 0.1], [0.55, 0.42, 0.3, 1])
    _box(world, "desk", [rx, ry + 2.4, 0.55], [1.6, 0.45, 0.55], [0.36, 0.3, 0.25, 1])
    _box(world, "desk_top", [rx, ry + 2.4, 1.12], [1.7, 0.52, 0.03], [0.93, 0.92, 0.9, 1])

    # Dos AGIBOT X2 Ultra oficiales: 01 en recepción mirando al acceso; 02 en recepción VIP.
    robot1_yaw = -math.pi / 2  # el acceso principal queda al sur
    vx, vy = nodes_xy["recepcion_vip"]
    robot2_xy, robot2_yaw = (vx, vy + 1.5), -math.pi / 2
    for prefix, xy, yaw in (("r1_", (rx, ry + 1.2), robot1_yaw), ("r2_", robot2_xy, robot2_yaw)):
        robot = mujoco.MjSpec.from_file(str(MODEL))
        frame = world.add_frame(pos=[*xy, 0], quat=yaw_quat(yaw))
        frame.attach_body(robot.body("pelvis"), prefix, "")
    _box(world, "vip_floor", [vx, vy + 1, 0.01], [4, 4, 0.01], [0.93, 0.89, 0.8, 1])

    for i, visitor in enumerate(visitors):
        _person(spec, visitor, (rx + 3 + i * 1.5, ry - 60))
    model = spec.compile()
    info = SceneInfo(club, s, nodes_xy, (rx, ry + 1.2), robot1_yaw, robot2_xy, robot2_yaw, visitors, edge_index)
    return model, info


def _near_segment(p, a, b, distance):
    (px, py), (ax, ay), (bx, by) = p, a, b
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy or 1)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy)) < distance
