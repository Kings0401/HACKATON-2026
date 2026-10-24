"""Saludo con la mano del Booster K1 (se ejecuta DENTRO del robot; lo sube booster_k1/saludar.ps1).

El firmware solo acepta gestos en WALK (en PREP responde código 400). Sin
--entrar-walk solo saluda si el robot ya está en WALK. Con --entrar-walk pasa
de PREP a WALK, saluda y vuelve a PREP. Nunca sale de DAMP ni camina.

    python3 saludar_k1.py --entrar-walk                         # PREP -> WALK, saluda ~4 s, vuelve a PREP
    python3 saludar_k1.py --entrar-walk --texto-b64 <base64>    # y además dice algo con espeak-ng
"""

from __future__ import annotations

import argparse
import base64
import shutil
import subprocess
import sys
import time

import booster_robotics_sdk_python as b

def esperar_modo(client, modo, segundos: float = 6.0) -> bool:
    fin = time.time() + segundos
    while time.time() < fin:
        if client.GetMode().mode == modo:
            return True
        time.sleep(0.2)
    return False


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser()
    p.add_argument("--segundos", type=float, default=4.0)
    p.add_argument("--texto-b64")
    p.add_argument("--entrar-walk", action="store_true", help="si está en PREP, pasa a WALK para saludar y vuelve")
    a = p.parse_args()

    b.ChannelFactory.Instance().Init(0, "127.0.0.1")
    client = b.B1LocoClient()
    client.Init()
    inicial = client.GetMode().mode
    if inicial == b.RobotMode.kPrepare and a.entrar_walk:
        print("PREP -> WALK…")
        client.ChangeMode(b.RobotMode.kWalking)
        if not esperar_modo(client, b.RobotMode.kWalking):
            sys.exit("El robot no entró en WALK; no saludo.")
        time.sleep(1.5)  # deja que el control de marcha se estabilice
    elif inicial != b.RobotMode.kWalking:
        sys.exit(f"No saludo: el robot está en {inicial.name}. Los gestos requieren WALK "
                 "(use --entrar-walk si está de pie en PREP).")

    voz = None
    if a.texto_b64 and shutil.which("espeak-ng"):
        texto = base64.b64decode(a.texto_b64).decode("utf-8")
        voz = subprocess.Popen(["espeak-ng", "-v", "es-419", "-s", "150", texto])
    try:
        print("Saludando…")
        client.WaveHand(b.HandAction.kHandOpen)
        try:
            time.sleep(max(1.0, min(a.segundos, 15.0)))
        finally:
            client.WaveHand(b.HandAction.kHandClose)  # baja la mano aunque se interrumpa
        if voz:
            voz.wait()
    finally:
        if inicial == b.RobotMode.kPrepare and client.GetMode().mode == b.RobotMode.kWalking:
            time.sleep(1.0)
            client.ChangeMode(b.RobotMode.kPrepare)  # vuelve a como estaba
            print("WALK -> PREP")
    print("Listo.")


if __name__ == "__main__":
    main()
