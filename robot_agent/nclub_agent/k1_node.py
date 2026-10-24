"""Agente de recepción N Club para el Booster K1 (firmware 1.8, ROS 2 Humble).

Comprobado en el K1 de N Club el 24-10-2026:
- Cámara de la cabeza en /booster_video_stream (CompressedImage JPEG, ~7 Hz, 544x306).
- Micrófono USB NationalChip: lo tiene en exclusiva el servicio de audio de Booster,
  así que se lee con AudioManager.CreateCaptureStream (PCM NAEC 16 kHz mono, con
  cancelación de eco). PulseAudio queda como respaldo.
- Parlante USB C-Media. La voz nativa LUI responde 400 en esta unidad, por eso se
  usa Piper (español, offline) y, si no está, espeak-ng.

Solo percibe, consulta a FastAPI y habla. El saludo con la mano (NCLUB_GESTOS=1)
se envía únicamente si el robot YA está en WALK: nunca cambia de modo ni camina.

    PYTHONPATH=~/nclub/robot_agent:~/nclub/vision python -m nclub_agent.k1_node
"""

from __future__ import annotations

import logging
import os
import queue
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from pathlib import Path

import cv2
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import CompressedImage

from nclub_vision.face import FaceEngine
from nclub_vision.qr import QrReader
from nclub_vision.sources import QueueFrameSource, decode_jpeg, encode_jpeg

from .backend_client import BackendClient, HeartbeatLoop
from .booster_camera import BoosterGallerySync
from .core import AgentConfig, LogSpeaker, ReceptionAgent
from .speech import SAMPLE_RATE, EnergyVAD, make_transcriber

log = logging.getLogger("nclub.k1")
CAMERA_TOPIC = "/booster_video_stream"
MAX_ANALYSIS_WIDTH = 1280


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


# ---------- voz del robot ----------

class QueuedSpeaker:
    """Habla en un hilo propio: ReceptionAgent llama speak() con su lock tomado."""

    def __init__(self, synth) -> None:
        self.synth = synth
        self.texts: queue.Queue[str] = queue.Queue()
        self.spoken: list[str] = []
        threading.Thread(target=self._run, daemon=True, name="nclub-k1-voz").start()

    def speak(self, text: str) -> None:
        self.spoken.append(text)
        log.info("ROBOT DICE: %s", text)
        self.texts.put(text)

    def _run(self) -> None:
        while True:
            text = self.texts.get()
            try:
                self.synth(text)
            except Exception as error:  # la voz falla sola; el agente sigue
                log.warning("No se pudo decir «%s»: %s", text[:40], error)


def piper_synth(model: str, player: list[str]):
    """Piper (pip install piper-tts) con un modelo .onnx en español."""
    from piper import PiperVoice

    voice = PiperVoice.load(model)

    def say(text: str) -> None:
        import wave

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            path = tmp.name
        try:
            with wave.open(path, "wb") as wav:
                if hasattr(voice, "synthesize_wav"):  # piper-tts >= 1.3
                    voice.synthesize_wav(text, wav)
                else:  # piper-tts 1.2
                    voice.synthesize(text, wav)
            subprocess.run([*player, path], check=True, timeout=60)
        finally:
            os.unlink(path)

    return say


def espeak_synth(text: str) -> None:
    subprocess.run(["espeak-ng", "-v", "es-419", "-s", "150", text], check=True, timeout=60)


def make_speaker(choice: str, piper_model: str):
    player = ["paplay"] if shutil.which("paplay") else ["aplay", "-q"]
    if choice in ("piper", "auto") and piper_model and Path(piper_model).is_file():
        try:
            speaker = QueuedSpeaker(piper_synth(piper_model, player))
            log.info("Voz: Piper (%s)", Path(piper_model).name)
            return speaker
        except Exception as error:
            log.warning("Piper no disponible (%s); uso espeak-ng", error)
    if choice != "none" and shutil.which("espeak-ng"):
        log.info("Voz: espeak-ng")
        return QueuedSpeaker(espeak_synth)
    log.warning("Sin voz: el robot solo registrará lo que diría")
    return LogSpeaker()


# ---------- SDK de Booster (una sola inicialización por proceso) ----------

_SDK = None


def booster_sdk():
    global _SDK
    if _SDK is None:
        import booster_robotics_sdk_python as b

        b.ChannelFactory.Instance().Init(0, "127.0.0.1")
        _SDK = b
    return _SDK


# ---------- micrófono ----------

class Transcriptions:
    """Transcribe una frase a la vez y solo con alguien frente al robot.

    El K1 no tiene palabra de activación como el X2: sin este filtro, la charla de
    fondo abriría sesiones y saturaría el CPU con Whisper.
    """

    def __init__(self, agent: ReceptionAgent, presence_s: float = 15.0) -> None:
        self.agent, self.presence_s = agent, presence_s
        self.pending: queue.Queue[bytes] = queue.Queue(maxsize=1)
        threading.Thread(target=self._run, daemon=True, name="nclub-k1-asr").start()

    def offer(self, pcm: bytes) -> None:
        state = self.agent.state
        if not state.session_id or self.agent.clock() - state.last_presence > self.presence_s:
            return  # nadie atendiéndose: charla de fondo
        try:
            self.pending.get_nowait()  # una frase vieja sin procesar se descarta
        except queue.Empty:
            pass
        try:
            self.pending.put_nowait(pcm)
        except queue.Full:
            pass

    def _run(self) -> None:
        while True:
            pcm = self.pending.get()
            self.agent.on_mic_state("procesando")
            try:
                self.agent.on_utterance(pcm)
            except Exception:
                log.exception("Error transcribiendo una frase")
            finally:
                self.agent.on_mic_state("escuchando")


class BoosterMic:
    """Micrófono del K1 a través del servicio de audio de Booster, que tiene el
    dispositivo en exclusiva. Usa el PCM NAEC (16 kHz mono, con cancelación de eco)."""

    def __init__(self, agent: ReceptionAgent, asr: Transcriptions) -> None:
        b = booster_sdk()
        self.agent, self.asr = agent, asr
        self.chunks: queue.Queue[bytes] = queue.Queue(maxsize=400)
        self.stopped = threading.Event()
        self.manager = b.AudioManager()
        self.manager.Init()
        self.stream = self.manager.CreateCaptureStream()
        options = b.AudioCaptureStreamOptions()
        options.enable_naec_pcm, options.enable_raw_pcm = True, False
        self.stream.Init(options)
        self.stream.SetFrameCallback(self._on_frame)
        self.stream.SetErrorCallback(lambda error: log.warning("Error de audio Booster: %s", error))
        self.name = "booster:naec"

    def _on_frame(self, frame) -> None:
        # Corre en un hilo del SDK: una excepción aquí termina el proceso, así que solo se encola.
        try:
            if frame.naec_valid and frame.naec_format.sample_rate_hz == SAMPLE_RATE:
                self.chunks.put_nowait(np.asarray(frame.naec_pcm, dtype=np.int16).tobytes())
        except Exception:
            pass

    def start(self) -> None:
        threading.Thread(target=self._run, daemon=True, name="nclub-k1-mic").start()
        self.stream.Start()

    def _run(self) -> None:
        vad = EnergyVAD()
        self.agent.on_mic_state("escuchando")
        while not self.stopped.is_set():
            try:
                pcm = self.chunks.get(timeout=1)
            except queue.Empty:
                continue
            self.agent.last_audio_at, self.agent.mic_ok = self.agent.clock(), True
            for utterance in vad.feed(pcm):
                self.asr.offer(utterance)

    def stop(self) -> None:
        self.stopped.set()
        try:
            self.stream.Stop()
            self.stream.Destroy()
        except Exception:
            pass


def pick_mic_source(preferred: str) -> str | None:
    if preferred:
        return preferred
    try:
        out = subprocess.run(["pactl", "list", "short", "sources"], capture_output=True, text=True, timeout=5).stdout
    except Exception:
        return None
    sources = [line.split("\t")[1] for line in out.splitlines() if "\t" in line]
    inputs = [s for s in sources if not s.endswith(".monitor")]
    return next((s for s in inputs if "NationalChip" in s), inputs[0] if inputs else None)


class MicLoop(threading.Thread):
    """parec (PulseAudio) -> PCM 16 kHz mono -> EnergyVAD -> agent.on_utterance."""

    def __init__(self, agent: ReceptionAgent, source: str, asr: Transcriptions) -> None:
        super().__init__(daemon=True, name="nclub-k1-mic")
        self.agent, self.source, self.asr = agent, source, asr
        self.name = f"pulse:{source}"
        self.stopped = threading.Event()
        self.proc: subprocess.Popen | None = None

    def run(self) -> None:
        vad = EnergyVAD()
        chunk = SAMPLE_RATE * 2 // 10  # 100 ms
        while not self.stopped.is_set():
            self.proc = subprocess.Popen(
                ["parec", f"--device={self.source}", f"--rate={SAMPLE_RATE}", "--channels=1",
                 "--format=s16le", "--latency-msec=60"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            self.agent.on_mic_state("escuchando")
            while not self.stopped.is_set():
                data = self.proc.stdout.read(chunk)
                if not data:
                    break
                self.agent.last_audio_at, self.agent.mic_ok = self.agent.clock(), True
                for utterance in vad.feed(data):
                    self.asr.offer(utterance)
            self.proc.kill()
            if not self.stopped.is_set():
                log.warning("El micrófono se cortó; reintento en 3 s")
                self.agent.on_mic_state("sin audio")
                self.stopped.wait(3)

    def stop(self) -> None:
        self.stopped.set()
        if self.proc:
            self.proc.kill()


# ---------- saludo opcional ----------

class WaveGesture:
    """Saluda con la mano al abrir sesión, solo si el robot ya está en WALK."""

    def __init__(self) -> None:
        b = self.b = booster_sdk()
        self.client = b.B1LocoClient()
        self.client.Init()
        self.last = 0.0

    def wave(self) -> None:
        if time.time() - self.last < 15:
            return
        self.last = time.time()
        threading.Thread(target=self._wave, daemon=True, name="nclub-k1-saludo").start()

    def _wave(self) -> None:
        b = self.b
        try:
            mode = self.client.GetMode().mode
            if mode != b.RobotMode.kWalking:
                log.info("Saludo omitido: el robot está en %s (los gestos requieren WALK)", mode.name)
                return
            self.client.WaveHand(b.HandAction.kHandOpen)
            time.sleep(3.5)
            self.client.WaveHand(b.HandAction.kHandClose)
        except Exception as error:
            log.warning("No se pudo saludar: %s", error)


# ---------- nodo ----------

class K1Node(Node):
    def __init__(self, frames: QueueFrameSource, topic: str) -> None:
        super().__init__("nclub_k1_agent")
        self.frames, self.dropped = frames, 0
        self.create_subscription(CompressedImage, topic, self._on_jpeg, qos_profile_sensor_data)

    def _on_jpeg(self, msg: CompressedImage) -> None:
        data = bytes(msg.data)
        if not data.rstrip(b"\x00").endswith(b"\xff\xd9"):  # fotograma truncado
            self.dropped += 1
            return
        frame = decode_jpeg(data)
        if frame is None:
            return
        if frame.shape[1] > MAX_ANALYSIS_WIDTH:
            scale = MAX_ANALYSIS_WIDTH / frame.shape[1]
            frame = cv2.resize(frame, (MAX_ANALYSIS_WIDTH, int(frame.shape[0] * scale)))
        self.frames.push(frame)


def main() -> None:
    logging.basicConfig(level=env("NCLUB_LOG_LEVEL", "INFO").upper(),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # un registro por fotograma tapa lo importante
    api_url, robot_key = env("NCLUB_API_URL").rstrip("/"), env("NCLUB_ROBOT_KEY")
    if not api_url or not robot_key:
        raise SystemExit("Defina NCLUB_API_URL y NCLUB_ROBOT_KEY (archivo ~/nclub/k1.env).")
    robot_id = env("NCLUB_ROBOT_ID", "robot1")
    topic = env("NCLUB_CAMERA_TOPIC", CAMERA_TOPIC)
    registro = Path(env("NCLUB_REGISTRO_DIR", "~/nclub/dataset/registro")).expanduser()

    client = BackendClient(api_url, robot_key, robot_id)
    registro.mkdir(parents=True, exist_ok=True)
    try:
        from nclub_vision.sync import sync

        report = sync(api_url, robot_key, registro)
        if report["errors"]:
            log.warning("Sincronización facial con errores: %s", "; ".join(report["errors"][:3]))
    except Exception as error:
        log.warning("No se pudo sincronizar la galería; uso la local: %s", error)
    face = FaceEngine()
    face.enroll_folder(registro)
    log.info("Reconocimiento facial listo: %d personas", len(face.gallery.identities))

    speaker = make_speaker(env("NCLUB_TTS", "auto"), env("NCLUB_PIPER_MODEL"))
    asr = env("NCLUB_ASR", "faster-whisper")
    transcriber = make_transcriber(asr, model=env("NCLUB_ASR_MODEL", "small"))
    agent = ReceptionAgent(client, face, QrReader(), speaker, transcriber, AgentConfig(), encode_jpeg=encode_jpeg)
    if env("NCLUB_GESTOS", "0") in ("1", "true", "si"):
        try:
            gesture = WaveGesture()
            agent.on_session_start = gesture.wave
            log.info("Saludo con la mano ACTIVADO (solo si el robot está en WALK)")
        except Exception as error:
            log.warning("Saludo no disponible: %s", error)

    mic = None
    if asr != "none":
        try:
            mic = BoosterMic(agent, Transcriptions(agent))
        except Exception as error:  # firmware sin captura por SDK: se intenta PulseAudio
            log.warning("Micrófono Booster no disponible (%s); pruebo PulseAudio", error)
            source = pick_mic_source(env("NCLUB_MIC_SOURCE"))
            mic = MicLoop(agent, source, Transcriptions(agent)) if source and shutil.which("parec") else None
    if mic:
        mic.start()
        log.info("Micrófono: %s", mic.name)
    else:
        log.warning("Sin micrófono: el robot no escuchará")

    heartbeat = HeartbeatLoop(client, lambda: {
        **agent.status(), "name": env("NCLUB_ROBOT_NAME", "Booster K1"), "model": "Booster K1",
        "firmware": env("NCLUB_FIRMWARE") or None, "camera_topic": topic,
        "audio_topic": mic.name if mic else "",
    })
    gallery = BoosterGallerySync(client, face, registro, interval=float(env("NCLUB_GALLERY_POLL_S", "5")))
    frames = QueueFrameSource(maxsize=1)

    def vision_loop() -> None:
        for frame in frames.frames():
            try:
                agent.on_frame(frame)
            except Exception:
                log.exception("Error procesando un fotograma")
                time.sleep(0.5)

    rclpy.init()
    node = K1Node(frames, topic)
    threading.Thread(target=vision_loop, daemon=True, name="nclub-k1-vision").start()
    heartbeat.start()
    gallery.start()
    log.info("Agente K1 activo · cámara %s · backend %s · robot_id %s", topic, api_url, robot_id)
    signal.signal(signal.SIGTERM, lambda *_: rclpy.try_shutdown())
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, Exception) as error:
        if not isinstance(error, KeyboardInterrupt) and rclpy.ok():
            log.exception("El nodo se detuvo")
    finally:
        if mic:
            mic.stop()
        gallery.stop()
        heartbeat.stop()
        frames.close()
        agent.end_session()
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
