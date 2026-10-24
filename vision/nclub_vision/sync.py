"""Sincroniza fotografías de registro desde FastAPI (bucket privado rostros-nclub).

Causa del error histórico al descargar: los nombres con espacios o paréntesis
("WhatsApp Image … (1).jpeg") no pasaban la validación del backend (400) y
cualquier fallo de Storage se respondía como 404. Además, un archivo fallido
abortaba el resto de la persona. Ahora el backend valida contra el listado
real del bucket, el cliente codifica el nombre y cada archivo se reporta solo.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from urllib.parse import quote

import cv2
import httpx
import numpy as np


def sync(api_url: str, robot_key: str, target: Path, personas: list[str] | None = None) -> dict:
    report = {"downloaded": 0, "unchanged": 0, "errors": []}
    headers = {"X-Robot-Key": robot_key}
    with httpx.Client(base_url=api_url.rstrip("/"), headers=headers, timeout=20) as client:
        if not personas:
            response = client.get("/rostros")
            response.raise_for_status()
            personas = response.json()["personas"]
        for persona_id in personas:
            try:
                response = client.get(f"/rostros/{quote(persona_id, safe='')}")
                response.raise_for_status()
                names = response.json()["fotografias"]
            except (httpx.HTTPError, KeyError, ValueError) as error:
                report["errors"].append(f"{persona_id}: {error}")
                continue
            folder = target / persona_id
            folder.mkdir(parents=True, exist_ok=True)
            for name in names:
                destination = folder / Path(name).name
                try:
                    image = client.get(
                        f"/rostros/{quote(persona_id, safe='')}/{quote(name, safe='')}"
                    )
                    image.raise_for_status()
                    content = image.content
                    if cv2.imdecode(np.frombuffer(content, np.uint8), cv2.IMREAD_COLOR) is None:
                        report["errors"].append(f"{persona_id}/{name}: archivo no es una imagen")
                        continue
                    if destination.is_file() and destination.read_bytes() == content:
                        report["unchanged"] += 1
                        continue
                    destination.write_bytes(content)
                    report["downloaded"] += 1
                except httpx.HTTPStatusError as error:
                    detail = error.response.text[:120]
                    report["errors"].append(f"{persona_id}/{name}: HTTP {error.response.status_code} {detail}")
                except httpx.HTTPError as error:
                    report["errors"].append(f"{persona_id}/{name}: {error}")
    return report


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--dest", default="dataset/registro")
    parser.add_argument("personas", nargs="*")
    args = parser.parse_args()
    api_url, key = os.getenv("NCLUB_API_URL", ""), os.getenv("ROBOT_API_KEY", "")
    if not api_url or not key:
        raise SystemExit("Faltan NCLUB_API_URL o ROBOT_API_KEY en .env")
    report = sync(api_url, key, Path(args.dest), args.personas or None)
    for error in report["errors"]:
        print("  Error:", error)
    print(
        f"Sincronización terminada: {report['downloaded']} nuevas, "
        f"{report['unchanged']} sin cambios, {len(report['errors'])} errores."
    )


if __name__ == "__main__":
    main()
