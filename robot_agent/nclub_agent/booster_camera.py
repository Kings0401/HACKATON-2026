"""Agente de reconocimiento facial para cámaras BoosterOS (K1/T1/T2).

Solo consume imágenes RGB del Booster y las entrega al mismo FaceEngine,
lector QR y backend que usa el agente ROS 2 del AGIBOT. No envía comandos de
movimiento al robot.
"""

from __future__ import annotations

import logging
import os
import shutil
import signal
import threading
import time
from pathlib import Path

import cv2
import numpy as np

from nclub_vision.face import FaceEngine
from nclub_vision.qr import QrReader
from nclub_vision.sources import QueueFrameSource, encode_jpeg

from .backend_client import BackendClient, HeartbeatLoop
from .core import AgentConfig, LogSpeaker, ReceptionAgent

log = logging.getLogger("nclub.booster")
MAX_ANALYSIS_WIDTH = 1280


def booster_image_to_bgr(image) -> np.ndarray:
    """Convierte un AnyImage RGB de BoosterOS a BGR para OpenCV."""
    frame = np.asarray(image.to_numpy())
    if frame.ndim == 2:
        return cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
    if frame.ndim != 3:
        raise ValueError(f"Formato de imagen Booster no compatible: {frame.shape}")
    channels = frame.shape[2]
    if channels == 3:
        return cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
    if channels == 4:
        return cv2.cvtColor(frame, cv2.COLOR_RGBA2BGR)
    raise ValueError(f"La cámara debe entregar RGB/RGBA, llegó {channels} canales")


class BoosterGallerySync(threading.Thread):
    """Actualiza la galería facial local cuando cambia Storage privado."""

    def __init__(self, client: BackendClient, face: FaceEngine, root: Path, interval: float = 5.0):
        super().__init__(daemon=True, name="nclub-booster-gallery")
        self.client, self.face, self.root, self.interval = client, face, root, interval
        self.stopped = threading.Event()
        self.version: str | None = None

    def _refresh(self, manifest: dict) -> None:
        from nclub_vision.sync import sync

        temp_root = self.root.with_name(f"{self.root.name}.sync-tmp")
        shutil.rmtree(temp_root, ignore_errors=True)
        temp_root.mkdir(parents=True, exist_ok=True)
        report = sync(str(self.client.http.base_url).rstrip("/"),
                      self.client.http.headers["X-Robot-Key"], temp_root)
        if report["errors"]:
            shutil.rmtree(temp_root, ignore_errors=True)
            raise RuntimeError("; ".join(report["errors"][:3]))
        fresh = FaceEngine()
        fresh.enroll_folder(temp_root)
        self.face.gallery.features = fresh.gallery.features
        self.face.gallery.skipped = fresh.gallery.skipped
        shutil.rmtree(self.root, ignore_errors=True)
        temp_root.rename(self.root)
        self.version = manifest.get("version")
        log.info("Galería Booster actualizada: %d personas, %d fotos nuevas",
                 len(self.face.gallery.identities), report["downloaded"])

    def run(self) -> None:
        while not self.stopped.is_set():
            try:
                manifest = self.client.gallery()
                if manifest.get("version") != self.version:
                    self._refresh(manifest)
            except Exception as error:
                log.warning("No se pudo actualizar la galería facial: %s", error)
            self.stopped.wait(self.interval)

    def stop(self) -> None:
        self.stopped.set()


def main() -> None:
    from boosteros.robots.booster import BoosterRobot

    logging.basicConfig(
        level=os.environ.get("NCLUB_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    api_url = os.environ.get("NCLUB_API_URL", "").rstrip("/")
    robot_key = os.environ.get("NCLUB_ROBOT_KEY", "")
    robot_id = os.environ.get("NCLUB_ROBOT_ID", "robot1")
    camera_id = os.environ.get("NCLUB_BOOSTER_CAMERA_ID", "")
    gallery_dir = Path(os.environ.get("NCLUB_REGISTRO_DIR", "~/nclub/dataset/registro")).expanduser()
    if not api_url or not robot_key:
        raise SystemExit("Defina NCLUB_API_URL y NCLUB_ROBOT_KEY antes de iniciar el agente Booster.")

    # BoosterRobot conserva un único cliente de cámara y no se usa para mover
    # el robot; la cámara queda elegida por ID o usa la predeterminada del SDK.
    robot = BoosterRobot()
    info = robot.robot_info
    log.info("Booster conectado: %s · %s", getattr(info, "manufacturer", "Booster"),
             getattr(info, "model", "modelo sin informar"))
    try:
        cameras = [sensor for sensor in robot.list_sensors() if getattr(sensor, "sensor_type", "") == "camera"]
        log.info("Cámaras Booster: %s", ", ".join(
            f"{getattr(sensor, 'id', '?')} ({getattr(sensor, 'model', 'sin modelo')})" for sensor in cameras
        ) or "el SDK no informó cámaras")
    except Exception as error:
        log.warning("No se pudo consultar la lista de cámaras Booster: %s", error)
    client = BackendClient(api_url, robot_key, robot_id)
    face = FaceEngine()
    gallery_dir.mkdir(parents=True, exist_ok=True)
    try:
        from nclub_vision.sync import sync

        sync_report = sync(api_url, robot_key, gallery_dir)
        if sync_report["errors"]:
            log.warning("Sincronización facial inicial con errores: %s", "; ".join(sync_report["errors"][:3]))
    except Exception as error:
        log.warning("No se pudo sincronizar Storage; se usará la galería local: %s", error)
    face.enroll_folder(gallery_dir)
    log.info("Reconocimiento facial listo: %d personas registradas", len(face.gallery.identities))

    frames = QueueFrameSource(maxsize=1)
    agent = ReceptionAgent(
        client,
        face,
        QrReader(),
        LogSpeaker(),
        config=AgentConfig(),
        encode_jpeg=encode_jpeg,
    )
    robot_name = getattr(info, "model", "Booster")
    heartbeat = HeartbeatLoop(client, lambda: {
        **agent.status(),
        "name": robot_name,
        "model": robot_name,
        "firmware": getattr(info, "firmware_version", None),
        "camera_topic": f"boosteros:{camera_id or 'default'}",
        "audio_topic": "",
    })

    callback_errors = 0

    def on_image(image) -> None:
        nonlocal callback_errors
        try:
            frame = booster_image_to_bgr(image)
            if frame.shape[1] > MAX_ANALYSIS_WIDTH:
                scale = MAX_ANALYSIS_WIDTH / frame.shape[1]
                frame = cv2.resize(frame, (MAX_ANALYSIS_WIDTH, int(frame.shape[0] * scale)))
            frames.push(frame)
        except Exception as error:
            callback_errors += 1
            if callback_errors == 1 or callback_errors % 100 == 0:
                log.warning("No se pudo procesar imagen Booster (%d): %s", callback_errors, error)

    subscription = robot.subscribe_image(
        on_image,
        camera_id=camera_id,
        img_type="rgb",
        queue_size=1,
        overflow="drop_oldest",
    )
    gallery = BoosterGallerySync(client, face, gallery_dir)
    heartbeat.start()
    gallery.start()
    def vision_loop() -> None:
        for frame in frames.frames():
            try:
                agent.on_frame(frame)
            except Exception:
                log.exception("Error procesando un fotograma de la cámara Booster")

    worker = threading.Thread(target=vision_loop, daemon=True, name="nclub-booster-vision")
    worker.start()
    stopped = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stopped.set())
    log.info("Cámara Booster activa: %s", camera_id or "predeterminada")
    try:
        while not stopped.wait(1):
            pass
    except KeyboardInterrupt:
        pass
    finally:
        subscription.unsubscribe()
        gallery.stop()
        heartbeat.stop()
        frames.close()
        agent.end_session()


if __name__ == "__main__":
    main()
