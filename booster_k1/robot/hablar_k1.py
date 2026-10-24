"""Hace hablar al Booster K1. Se ejecuta DENTRO del robot (lo sube booster_k1/hablar.ps1).

    python3 hablar_k1.py --texto-b64 <base64 utf-8>     # sintetiza y reproduce por el parlante
    python3 hablar_k1.py --wav saludo.wav               # reproduce un WAV PCM
    python3 hablar_k1.py --voces                        # lista las voces del SDK
    python3 hablar_k1.py --diagnostico                  # qué motores de voz hay en el robot

Motores, en orden con --motor auto:
  1. boosteros (SDK oficial, firmware >= v1.7): Speech.synthesize + audio_manager.play_stream.
  2. sistema: espeak-ng / espeak del robot (voz robótica, solo para probar el parlante).
Para WAV: boosteros.play_stream, y si no está, aplay.
"""

from __future__ import annotations

import argparse
import base64
import shutil
import subprocess
import sys
import wave

CHUNK = 4096


def _robot():
    from boosteros.robots.booster import BoosterRobot

    return BoosterRobot()


def _play_pcm(robot, data: bytes, sample_rate: int, channels: int, sample_format="S16LE",
              volume: float | None = None) -> None:
    stream = robot.audio_manager.play_stream(sample_rate=sample_rate, channels=channels,
                                             sample_format=sample_format, volume=volume)
    for i in range(0, len(data), CHUNK):
        stream.write(data[i:i + CHUNK])
    stream.close()
    stream.wait()


def hablar_boosteros(texto: str, voz: str, velocidad: float, volumen: float | None) -> str:
    from boosteros.brain import Speech

    robot = _robot()
    audio = Speech(robot).synthesize(texto, voice=voz, speed=velocidad).result()
    _play_pcm(robot, bytes(audio.data), audio.sample_rate, audio.channels, audio.sample_format, volumen)
    return f"boosteros, voz '{voz}', {audio.duration.seconds:.1f} s"


def hablar_sistema(texto: str) -> str:
    for motor in ("espeak-ng", "espeak"):
        if shutil.which(motor):
            subprocess.run([motor, "-v", "es-419", "-s", "150", texto], check=True)
            return motor
    raise RuntimeError("el robot no tiene espeak-ng ni espeak")


def reproducir_wav(ruta: str, volumen: float | None) -> str:
    try:
        robot = _robot()
    except ImportError:
        if not shutil.which("aplay"):
            raise RuntimeError("no hay boosteros ni aplay para reproducir el WAV")
        subprocess.run(["aplay", "-q", ruta], check=True)
        return "aplay"
    with wave.open(ruta, "rb") as wav:
        if wav.getsampwidth() != 2:
            raise RuntimeError("el WAV debe ser PCM de 16 bits")
        _play_pcm(robot, wav.readframes(wav.getnframes()), wav.getframerate(), wav.getnchannels(), volume=volumen)
    return "boosteros (play_stream)"


def voces() -> None:
    from boosteros.brain import Speech

    for v in Speech(_robot()).list_voices():
        print(f"{v.get('id'):<28} {v.get('name', ''):<24} {v.get('gender', ''):<8} {','.join(v.get('capabilities', []))}")


def diagnostico() -> None:
    try:
        import boosteros

        print("boosteros:", getattr(boosteros, "__version__", "instalado"))
        robot = _robot()
        info = robot.robot_info
        print("robot:", info.manufacturer, info.model, info.serial_number)
        print("volumen del sistema:", robot.audio_manager.get_system_volume())
    except Exception as error:  # se informa y se sigue con lo demás
        print("boosteros: no disponible ->", type(error).__name__, error)
    for herramienta in ("espeak-ng", "espeak", "aplay", "pactl"):
        print(f"{herramienta}:", shutil.which(herramienta) or "no")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser()
    p.add_argument("--texto-b64", help="texto en UTF-8 codificado en base64 (evita problemas de comillas por SSH)")
    p.add_argument("--wav")
    p.add_argument("--voz", default="default")
    p.add_argument("--velocidad", type=float, default=1.0)
    p.add_argument("--volumen", type=float, help="0.0 a 1.0")
    p.add_argument("--motor", choices=("auto", "boosteros", "sistema"), default="auto")
    p.add_argument("--voces", action="store_true")
    p.add_argument("--diagnostico", action="store_true")
    a = p.parse_args()
    if a.diagnostico:
        return diagnostico()
    if a.voces:
        return voces()
    if a.wav:
        print("Reproducido con", reproducir_wav(a.wav, a.volumen))
        return
    if not a.texto_b64:
        p.error("indique --texto-b64, --wav, --voces o --diagnostico")
    texto = base64.b64decode(a.texto_b64).decode("utf-8")
    if a.motor in ("auto", "boosteros"):
        try:
            print("Dicho con", hablar_boosteros(texto, a.voz, a.velocidad, a.volumen))
            return
        except Exception as error:
            if a.motor == "boosteros":
                raise
            print(f"boosteros no pudo hablar ({type(error).__name__}: {error}); pruebo la voz del sistema")
    print("Dicho con", hablar_sistema(texto))


if __name__ == "__main__":
    main()
