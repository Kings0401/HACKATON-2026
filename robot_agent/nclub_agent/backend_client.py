"""Cliente FastAPI del agente con reintentos, estado de conexión y reconexión."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

import httpx

log = logging.getLogger(__name__)


class BackendError(RuntimeError):
    """El backend respondió con un error de cliente (4xx)."""


class BackendUnavailable(BackendError):
    """Sin conexión o error del servidor: se reintenta y se informa al visitante."""


class BackendClient:
    def __init__(self, base_url: str, robot_key: str, robot_id: str, timeout: float = 5.0,
                 transport: httpx.BaseTransport | None = None, client: httpx.Client | None = None):
        self.robot_id = robot_id
        self.http = client or httpx.Client(
            base_url=base_url.rstrip("/"), timeout=timeout, transport=transport,
            headers={"X-Robot-Key": robot_key},
        )
        if client is not None:
            self.http.headers["X-Robot-Key"] = robot_key
        self.online = False
        self.failures = 0
        self.last_error: str | None = None
        self._listeners: list[Callable[[bool], None]] = []
        self._lock = threading.Lock()

    def on_status(self, listener: Callable[[bool], None]) -> None:
        self._listeners.append(listener)

    def _set_online(self, online: bool, error: str | None = None) -> None:
        changed = online != self.online
        self.online, self.last_error = online, error
        self.failures = 0 if online else self.failures + 1
        if changed:
            log.info("Backend %s", "conectado" if online else f"desconectado: {error}")
            for listener in self._listeners:
                listener(online)

    def request(self, method: str, path: str, retries: int = 2, **kwargs) -> dict:
        delay = 0.3
        for attempt in range(retries + 1):
            try:
                with self._lock:
                    response = self.http.request(method, path, **kwargs)
                if response.status_code >= 500:
                    raise httpx.HTTPStatusError("server", request=response.request, response=response)
                self._set_online(True)
                if response.status_code >= 400:
                    detail = response.json().get("detail") if response.headers.get("content-type", "").startswith("application/json") else response.text
                    raise BackendError(f"HTTP {response.status_code}: {detail}")
                return response.json()
            except (httpx.TransportError, httpx.HTTPStatusError) as error:
                self._set_online(False, str(error))
                if attempt == retries:
                    raise BackendUnavailable(str(error)) from error
                time.sleep(delay)
                delay *= 2
        raise BackendUnavailable("sin respuesta")

    # ---------- API del robot ----------

    def heartbeat(self, **status) -> dict:
        return self.request("POST", f"/robot/{self.robot_id}/heartbeat", json=status, retries=0)

    def push_frame(self, jpeg: bytes) -> None:
        self.request("PUT", f"/robot/{self.robot_id}/frame", content=jpeg,
                     headers={"Content-Type": "image/jpeg"}, retries=0)

    def start_session(self, simulated: bool = False) -> dict:
        return self.request("POST", "/robot/sessions", json={"robot_id": self.robot_id, "simulated": simulated})

    def face(self, session_id: str, observation: dict) -> dict:
        return self.request("POST", f"/robot/sessions/{session_id}/faces", json=observation)

    def credential(self, session_id: str, payload: str, kind: str) -> dict:
        return self.request("POST", f"/robot/sessions/{session_id}/credentials", json={"payload": payload, "kind": kind})

    def utterance(self, session_id: str, **body) -> dict:
        return self.request("POST", f"/robot/sessions/{session_id}/utterances", json=body)

    def resolve(self, session_id: str) -> dict:
        return self.request("POST", f"/robot/sessions/{session_id}/resolve")

    def close(self, session_id: str) -> dict:
        return self.request("POST", f"/robot/sessions/{session_id}/close", json={}, retries=0)


class HeartbeatLoop(threading.Thread):
    """Latido periódico con espera exponencial cuando el backend no responde."""

    def __init__(self, client: BackendClient, status: Callable[[], dict], interval: float = 5.0):
        super().__init__(daemon=True, name="nclub-heartbeat")
        self.client, self.status, self.interval = client, status, interval
        self.stopped = threading.Event()

    def run(self) -> None:
        wait = self.interval
        while not self.stopped.is_set():
            try:
                self.client.heartbeat(**self.status())
                wait = self.interval
            except BackendError:
                wait = min(wait * 2, 30.0)
            self.stopped.wait(wait)

    def stop(self) -> None:
        self.stopped.set()
