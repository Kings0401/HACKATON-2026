"""Descarga el modelo oficial del AGIBOT X2 Ultra para MuJoCo (una sola vez).

    python simulation/download_model.py

Fuente: https://github.com/AgibotTech/agibot_x2_urdf (X2_URDF-v1.3.0, licencia
Mulan PSL v2). Solo baja el MJCF y las mallas que usa, y agrega la cámara de la
frente (head_cam) en la cabeza del robot. Los archivos quedan en
simulation/models/x2_ultra (no se versionan).

Las mallas oficiales suman ~3.9 millones de triángulos; para renderizar rápido
se genera además una copia visual simplificada (meshes_lite, agrupación de
vértices a 6 mm) y x2_ultra_lite.xml. La cinemática y las dimensiones son las
mismas: solo cambia el detalle de la superficie.
"""

from __future__ import annotations

import re
import struct
import sys
import urllib.request
from pathlib import Path

import numpy as np

BASE = "https://raw.githubusercontent.com/AgibotTech/agibot_x2_urdf/main"
VERSION = "X2_URDF-v1.3.0"  # X2 Ultra. Para el "X2 Ultra -N" usar v1.4.0 (X2-Ultra.xml)
OUT = Path(__file__).resolve().parent / "models" / "x2_ultra"

# Cámara de la frente: mira hacia +X de la cabeza (MuJoCo mira por -Z de la cámara).
HEAD_CAMERA = '<camera name="head_cam" pos="0.075 0 0.035" xyaxes="0 -1 0 0 0 1" fovy="68" />'


def fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read()


LITE_CELL_M = 0.006


def read_stl(path: Path) -> np.ndarray:
    """Triángulos (n, 3, 3) de un STL binario."""
    raw = path.read_bytes()
    n = struct.unpack_from("<I", raw, 80)[0]
    if len(raw) != 84 + 50 * n:
        raise ValueError(f"{path.name}: solo se admite STL binario")
    rec = np.frombuffer(raw, dtype=np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")]), count=n, offset=84)
    return rec["v"].astype(np.float64)


def write_stl(path: Path, tris: np.ndarray) -> None:
    rec = np.zeros(len(tris), dtype=np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")]))
    normals = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    normals /= np.linalg.norm(normals, axis=1, keepdims=True) + 1e-12
    rec["n"], rec["v"] = normals, tris
    path.write_bytes(bytes(80) + struct.pack("<I", len(tris)) + rec.tobytes())


def simplify(tris: np.ndarray, cell: float = LITE_CELL_M) -> np.ndarray:
    """Agrupa vértices en una rejilla y descarta triángulos degenerados."""
    verts = tris.reshape(-1, 3)
    keys = np.floor(verts / cell).astype(np.int64)
    _, inverse = np.unique(keys, axis=0, return_inverse=True)
    inverse = inverse.reshape(-1)
    sums = np.zeros((inverse.max() + 1, 3))
    np.add.at(sums, inverse, verts)
    centers = sums / np.bincount(inverse)[:, None]
    faces = inverse.reshape(-1, 3)
    faces = faces[(faces[:, 0] != faces[:, 1]) & (faces[:, 1] != faces[:, 2]) & (faces[:, 0] != faces[:, 2])]
    _, first = np.unique(np.sort(faces, axis=1), axis=0, return_index=True)
    return centers[faces[np.sort(first)]]


def make_lite(xml: str) -> None:
    lite = OUT / "meshes_lite"
    lite.mkdir(exist_ok=True)
    before = after = 0
    for src in sorted((OUT / "meshes").glob("*")):
        target = lite / src.name
        tris = read_stl(src)
        small = simplify(tris) if len(tris) > 2000 else tris
        before, after = before + len(tris), after + len(small)
        if not target.is_file():
            write_stl(target, small)
    (OUT / "x2_ultra_lite.xml").write_text(xml.replace('meshdir="./meshes"', 'meshdir="./meshes_lite"'), encoding="utf-8")
    print(f"Mallas visuales simplificadas: {before:,} -> {after:,} triángulos")


def main() -> None:
    (OUT / "meshes").mkdir(parents=True, exist_ok=True)
    xml = fetch(f"{BASE}/{VERSION}/x2_ultra.xml").decode("utf-8")
    meshes = sorted(set(re.findall(r'file="([^"]+\.(?:STL|stl|obj))"', xml)))
    for i, name in enumerate(meshes, 1):
        target = OUT / "meshes" / name
        if not target.is_file():
            target.write_bytes(fetch(f"{BASE}/{VERSION}/meshes/{name}"))
        print(f"\r  mallas {i}/{len(meshes)}", end="", flush=True)
    print()
    if 'name="head_cam"' not in xml:
        xml = re.sub(r'(<body name="head_pitch_link"[^>]*>)', r"\1\n" + " " * 18 + HEAD_CAMERA, xml, count=1)
    (OUT / "x2_ultra.xml").write_text(xml, encoding="utf-8")
    if not (OUT / "LICENSE").is_file():
        (OUT / "LICENSE").write_bytes(fetch(f"{BASE}/LICENSE"))
    make_lite(xml)
    print(f"Modelo listo en {OUT} ({len(meshes)} mallas, licencia Mulan PSL v2)")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        main()
    except OSError as error:
        sys.exit(f"No se pudo descargar el modelo: {error}")
