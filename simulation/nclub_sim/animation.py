"""Animación cinemática: caminar de los visitantes y gestos de los X2.

La simulación es cinemática (mj_forward): se fijan posiciones articulares y
MuJoCo calcula la geometría, la cámara y el render. Así el X2 oficial se
mantiene de pie sin un controlador de equilibrio (que en el robot real provee
el control de movimiento de AGIBOT).
"""

from __future__ import annotations

import math

import mujoco
import numpy as np

from .scene import ROBOT_BASE_Z, yaw_quat

LIMB = ("hipj_l", "hipj_r", "kneej_l", "kneej_r", "shj_l", "shj_r", "elj_l", "elj_r")


def _qadr(model, name: str) -> int:
    return model.jnt_qposadr[model.joint(name).id]


class Rig:
    """Atajos a las direcciones qpos/mocap de robots y visitantes."""

    def __init__(self, model: mujoco.MjModel):
        self.model = model
        self.cache: dict[str, int] = {}

    def q(self, name: str) -> int:
        if name not in self.cache:
            self.cache[name] = _qadr(self.model, name)
        return self.cache[name]

    def mocap(self, body: str) -> int:
        return self.model.body(body).mocapid[0]


# ---------------- visitantes ----------------

def walk_pose(phase: float, amplitude: float = 1.0) -> dict[str, float]:
    s = math.sin(phase)
    c = math.cos(phase)
    a = amplitude
    return {
        "hipj_l": 0.45 * s * a, "hipj_r": -0.45 * s * a,
        "kneej_l": max(0.0, -0.75 * c) * a, "kneej_r": max(0.0, 0.75 * c) * a,
        "shj_l": -0.35 * s * a, "shj_r": 0.35 * s * a,
        "elj_l": -0.25 * a, "elj_r": -0.25 * a,
    }


def stand_pose() -> dict[str, float]:
    return {k: 0.0 for k in LIMB} | {"elj_l": -0.1, "elj_r": -0.1}


def present_qr_pose(t: float) -> dict[str, float]:
    """Levanta el teléfono a la altura de la cámara del robot (t de 0 a 1)."""
    k = min(1.0, max(0.0, t))
    k = k * k * (3 - 2 * k)
    pose = stand_pose()
    pose["shj_r"] = -0.8 * k  # codo junto al cuerpo, antebrazo horizontal
    pose["elj_r"] = -0.1 - 0.67 * k
    return pose


def set_person(data, rig: Rig, key: str, xy, yaw: float, pose: dict[str, float], z: float = 0.0):
    m = rig.mocap(f"v_{key}")
    data.mocap_pos[m] = [xy[0], xy[1], z]
    data.mocap_quat[m] = yaw_quat(yaw)
    for joint, angle in pose.items():
        data.qpos[rig.q(f"v_{key}_{joint}")] = angle


def hide_person(data, rig: Rig, key: str):
    data.mocap_pos[rig.mocap(f"v_{key}")] = [0, 0, -50]


# ---------------- AGIBOT X2 ----------------

def robot_pose(data, rig: Rig, prefix: str, xy, yaw: float, *, head_yaw=0.0, head_pitch=0.0,
               wave: float | None = None, t: float = 0.0, offer_hand: float = 0.0):
    """Postura del X2: de pie, respiración leve, cabeza orientable y saludo."""
    base = rig.q(f"{prefix}floating_base_joint")
    breath = 0.004 * math.sin(t * 1.6)
    data.qpos[base:base + 3] = [xy[0], xy[1], ROBOT_BASE_Z + breath]
    data.qpos[base + 3:base + 7] = yaw_quat(yaw)
    data.qpos[rig.q(f"{prefix}head_yaw_joint")] = float(np.clip(head_yaw, -0.349, 0.349))
    data.qpos[rig.q(f"{prefix}head_pitch_joint")] = float(np.clip(head_pitch, -0.3838, 0.3838))
    # Brazos relajados (ligeramente separados del torso).
    data.qpos[rig.q(f"{prefix}left_shoulder_roll_joint")] = 0.12
    data.qpos[rig.q(f"{prefix}right_shoulder_roll_joint")] = -0.12
    data.qpos[rig.q(f"{prefix}left_elbow_joint")] = -0.25
    data.qpos[rig.q(f"{prefix}right_elbow_joint")] = -0.25
    for side in ("left", "right"):
        data.qpos[rig.q(f"{prefix}{side}_shoulder_pitch_joint")] = 0.0
        data.qpos[rig.q(f"{prefix}{side}_shoulder_yaw_joint")] = 0.0
    if wave is not None:
        # Saludo (gesto 1002 del SDK): brazo derecho arriba y vaivén de la mano.
        k = max(0.0, min(1.0, wave / 0.6, (3.0 - wave) / 0.6))
        k = k * k * (3 - 2 * k)
        swing = 0.28 * math.sin(wave * 2 * math.pi * 1.4) * k
        data.qpos[rig.q(f"{prefix}right_shoulder_pitch_joint")] = -2.55 * k
        data.qpos[rig.q(f"{prefix}right_shoulder_roll_joint")] = -0.12 - 0.78 * k + swing
        data.qpos[rig.q(f"{prefix}right_shoulder_yaw_joint")] = 0.4 * k
        data.qpos[rig.q(f"{prefix}right_elbow_joint")] = -0.25 - 0.25 * k
    if offer_hand > 0:
        # Apretón de manos (gesto 1003): brazo derecho al frente.
        k = min(1.0, offer_hand)
        data.qpos[rig.q(f"{prefix}right_shoulder_pitch_joint")] = -0.9 * k
        data.qpos[rig.q(f"{prefix}right_elbow_joint")] = -0.25 - 0.45 * k


def look_at(robot_xy, robot_yaw: float, target_xyz, head_height: float = 1.32) -> tuple[float, float]:
    """Ángulos de cabeza para mirar un punto (limitados por las articulaciones)."""
    dx, dy = target_xyz[0] - robot_xy[0], target_xyz[1] - robot_xy[1]
    yaw = math.atan2(dy, dx) - robot_yaw
    yaw = (yaw + math.pi) % (2 * math.pi) - math.pi
    dist = math.hypot(dx, dy)
    pitch = -math.atan2(target_xyz[2] - head_height, max(dist, 0.3))
    return yaw, pitch
