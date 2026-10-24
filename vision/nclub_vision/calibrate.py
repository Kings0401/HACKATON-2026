"""Evalúa umbrales con fotografías de registro y de prueba.

    python -m nclub_vision.calibrate --registro dataset/registro --pruebas dataset/pruebas

Imprime puntuaciones genuinas/impostoras y el efecto de cada umbral. No
guarda imágenes ni plantillas. Con pocos ejemplos el resultado es
orientativo: repetir con fotografías reales del robot antes de producción.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2

from .face import IMAGE_SUFFIXES, FaceEngine

CANDIDATES = (0.30, 0.363, 0.40, 0.45, 0.50, 0.55, 0.60, 0.62, 0.65)


def evaluate(engine: FaceEngine, pruebas: Path, margin: float) -> dict:
    genuine, impostor, probes = [], [], []
    for folder in sorted(p for p in pruebas.iterdir() if p.is_dir()):
        for file in sorted(folder.iterdir()):
            if file.suffix.lower() not in IMAGE_SUFFIXES:
                continue
            image = cv2.imread(str(file))
            faces = engine.detect(image) if image is not None else []
            if len(faces) == 0:
                probes.append({"file": f"{folder.name}/{file.name}", "error": "sin rostro"})
                continue
            ranked = engine.best_scores(engine.embed(image, faces[0]))
            for pid, score in ranked:
                (genuine if pid == folder.name else impostor).append(score)
            probes.append({"file": f"{folder.name}/{file.name}", "truth": folder.name, "ranked": ranked})
    # Conjunto abierto: se retira la identidad verdadera para simular a un
    # visitante no registrado. Cualquier aceptación aquí es un falso positivo.
    full = dict(engine.gallery.features)
    unknown = []
    for p in probes:
        if "ranked" in p:
            ranked = [(i, s) for i, s in p["ranked"] if i != p["truth"]]
            if ranked:
                unknown.append(ranked)
    engine.gallery.features = full
    rows = []
    for t in CANDIDATES:
        open_false = sum(
            1
            for ranked in unknown
            if ranked[0][1] >= t and (len(ranked) < 2 or ranked[0][1] - ranked[1][1] >= margin)
        )
        correct = rejected = wrong = 0
        for p in probes:
            if "ranked" not in p:
                rejected += 1
                continue
            (best_id, best), *rest = p["ranked"]
            second = rest[0][1] if rest else -1
            if best < t or best - second < margin:
                rejected += 1
            elif best_id == p["truth"]:
                correct += 1
            else:
                wrong += 1
        rows.append(
            {
                "threshold": t,
                "correct": correct,
                "rejected": rejected,
                "false_accept": wrong,
                "unenrolled_false_accept": open_false,
                "unenrolled_trials": len(unknown),
            }
        )
    return {
        "genuine_min": min(genuine, default=None),
        "genuine_mean": sum(genuine) / len(genuine) if genuine else None,
        "impostor_max": max(impostor, default=None),
        "impostor_mean": sum(impostor) / len(impostor) if impostor else None,
        "probes": len(probes),
        "thresholds": rows,
        "details": [
            {"file": p["file"], "truth": p.get("truth"), "top": [(i, round(s, 3)) for i, s in p.get("ranked", [])[:2]], "error": p.get("error")}
            for p in probes
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registro", default="dataset/registro")
    parser.add_argument("--pruebas", default="dataset/pruebas")
    parser.add_argument("--margin", type=float, default=0.06)
    args = parser.parse_args()
    engine = FaceEngine()
    gallery = engine.enroll_folder(args.registro)
    report = evaluate(engine, Path(args.pruebas), args.margin)
    report["enrolled"] = {k: len(v) for k, v in gallery.features.items()}
    report["skipped"] = gallery.skipped
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
