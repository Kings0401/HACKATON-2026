"""Orígenes de fotogramas intercambiables.

El reconocimiento no depende de cv2.VideoCapture(0): en el robot, el nodo
ROS 2 empuja imágenes a QueueFrameSource; en desarrollo puede usarse una
webcam o una carpeta de imágenes.
"""

from __future__ import annotations

import queue
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Protocol

import cv2
import numpy as np

from .face import IMAGE_SUFFIXES


class FrameSource(Protocol):
    def frames(self) -> Iterator[np.ndarray]: ...
    def close(self) -> None: ...


def decode_jpeg(data: bytes) -> np.ndarray | None:
    """Decodifica sensor_msgs/CompressedImage (JPEG/MJPEG) a BGR."""
    if not data:
        return None
    return cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)


def rgb8_to_bgr(data: bytes, width: int, height: int, step: int | None = None) -> np.ndarray:
    """Convierte sensor_msgs/Image rgb8 (AimDK) a BGR sin cv_bridge."""
    step = step or width * 3
    arr = np.frombuffer(data, dtype=np.uint8).reshape(height, step)[:, : width * 3]
    return cv2.cvtColor(arr.reshape(height, width, 3), cv2.COLOR_RGB2BGR)


def encode_jpeg(frame: np.ndarray, quality: int = 70, max_width: int = 960) -> bytes:
    if frame.shape[1] > max_width:
        scale = max_width / frame.shape[1]
        frame = cv2.resize(frame, (max_width, int(frame.shape[0] * scale)))
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise ValueError("No se pudo codificar el fotograma")
    return buf.tobytes()


class QueueFrameSource:
    """Buffer de un solo fotograma: siempre procesa el más reciente."""

    def __init__(self, maxsize: int = 1, timeout: float = 1.0):
        self._queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=maxsize)
        self._closed = False
        self.timeout = timeout

    def push(self, frame: np.ndarray) -> None:
        if self._closed or frame is None:
            return
        try:
            self._queue.put_nowait(frame)
        except queue.Full:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
            self._queue.put_nowait(frame)

    def frames(self) -> Iterator[np.ndarray]:
        while not self._closed:
            try:
                yield self._queue.get(timeout=self.timeout)
            except queue.Empty:
                continue

    def close(self) -> None:
        self._closed = True


class ImageFolderSource:
    def __init__(self, folder: str | Path, delay: float = 0.0, loop: bool = False):
        self.files = sorted(
            p for p in Path(folder).rglob("*") if p.suffix.lower() in IMAGE_SUFFIXES
        )
        self.delay, self.loop = delay, loop

    def frames(self) -> Iterator[np.ndarray]:
        while True:
            for file in self.files:
                image = cv2.imread(str(file))
                if image is not None:
                    yield image
                    if self.delay:
                        time.sleep(self.delay)
            if not self.loop:
                return

    def close(self) -> None:
        pass


class OpenCVCameraSource:
    """Solo para desarrollo en un PC. El modo DEMO y el robot no lo usan."""

    def __init__(self, index: int = 0, backend: int = cv2.CAP_ANY):
        self.capture = cv2.VideoCapture(index, backend)
        if not self.capture.isOpened():
            raise RuntimeError(f"No se pudo abrir la cámara local {index}")

    def frames(self) -> Iterator[np.ndarray]:
        while True:
            ok, frame = self.capture.read()
            if not ok:
                return
            yield frame

    def close(self) -> None:
        self.capture.release()
