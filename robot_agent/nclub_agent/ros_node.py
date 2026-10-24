"""Nodo ROS 2 (Humble) del agente de recepción para AGIBOT X2 Ultra con AimDK.

Topics y servicios tomados de la documentación AimDK_X2 1.1.0
(https://x2-aimdk.agibot.com/en/latest/). NO verificados en el robot físico:
confirme con `ros2 topic list` / `ros2 topic info -v` en su firmware antes de
operar (ver robot_agent/README.md). El nodo no publica comandos de movimiento.

    ros2 run nclub_agent reception_agent --ros-args --params-file config/x2_ultra.yaml
"""

from __future__ import annotations

import os
import threading
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import CompressedImage, Image

from nclub_vision.face import FaceEngine
from nclub_vision.qr import QrReader
from nclub_vision.sources import QueueFrameSource, decode_jpeg, encode_jpeg, rgb8_to_bgr

from .backend_client import BackendClient, HeartbeatLoop
from .core import AgentConfig, LogSpeaker, ReceptionAgent
from .speech import VAD_BEGIN, VAD_END, VAD_PROCESSING, AimdkVadAssembler, make_transcriber

try:  # Mensajes del SDK AimDK (compilados desde aimdk_msgs del SDK del robot).
    from aimdk_msgs.msg import ProcessedAudioOutput, TtsPriorityLevel
    from aimdk_msgs.srv import PlayTts

    AIMDK = True
except ImportError:  # el agente sigue funcionando sin audio ni TTS
    AIMDK = False


class AimdkTtsSpeaker:
    """TTS por /aimdk_5Fmsgs/srv/PlayTts (campos según el ejemplo play_tts)."""

    def __init__(self, node: Node, service: str):
        self.node = node
        self.client = node.create_client(PlayTts, service)
        self.fallback = LogSpeaker()

    def speak(self, text: str) -> None:
        if not self.client.service_is_ready():
            self.node.get_logger().warning("Servicio TTS no disponible; texto: " + text)
            return
        request = PlayTts.Request()
        request.header.header.stamp = self.node.get_clock().now().to_msg()
        request.tts_req.text = text
        request.tts_req.domain = "nclub_reception"
        request.tts_req.is_interrupted = True
        request.tts_req.priority_level.value = TtsPriorityLevel.INTERACTION_L6
        self.client.call_async(request)  # no bloquear el hilo de percepción


class ReceptionAgentNode(Node):
    def __init__(self) -> None:
        super().__init__("nclub_reception_agent")
        p = self.declare_parameter
        backend_url = p("backend_url", "http://10.0.1.2:8000").value
        robot_id = p("robot_id", "robot1").value
        camera_topic = p("camera_topic", "/aima/hal/sensor/rgbd_head_front/rgb_image/compressed").value
        audio_topic = p("audio_topic", "/agent/process_audio_output").value
        registro = p("registro_dir", "/data/nclub/dataset/registro").value
        tts_enabled = p("tts_enabled", False).value
        tts_service = p("tts_service", "/aimdk_5Fmsgs/srv/PlayTts").value
        asr_engine = p("asr_engine", "faster-whisper").value
        asr_model = p("asr_model", "small").value
        self.rotate = p("rotate_90", False).value  # cámara trasera del X2 Ultra (new version)
        robot_key = os.environ.get("NCLUB_ROBOT_KEY", "")
        if not robot_key:
            raise RuntimeError("Defina NCLUB_ROBOT_KEY en el entorno (no en el YAML).")

        engine = FaceEngine()
        engine.enroll_folder(registro)
        self.get_logger().info(f"Galería facial: {engine.gallery.identities}")
        self.client = BackendClient(backend_url, robot_key, robot_id)
        speaker = AimdkTtsSpeaker(self, tts_service) if (tts_enabled and AIMDK) else LogSpeaker()
        self.agent = ReceptionAgent(
            self.client, engine, QrReader(), speaker,
            make_transcriber(asr_engine, model=asr_model), AgentConfig(), encode_jpeg=encode_jpeg,
        )
        self.frames = QueueFrameSource()
        threading.Thread(target=self._vision_loop, daemon=True, name="nclub-vision").start()
        self.heartbeat = HeartbeatLoop(self.client, lambda: {
            **self.agent.status(), "name": robot_id, "model": "AGIBOT X2 Ultra",
            "firmware": os.environ.get("NCLUB_FIRMWARE"), "sdk_version": os.environ.get("NCLUB_AIMDK_VERSION"),
            "camera_topic": camera_topic, "audio_topic": audio_topic,
        })
        self.heartbeat.start()

        camera_qos = QoSProfile(reliability=ReliabilityPolicy.BEST_EFFORT, history=HistoryPolicy.KEEP_LAST, depth=5)
        if camera_topic.endswith("/compressed"):
            self.create_subscription(CompressedImage, camera_topic, self._on_compressed, camera_qos)
        else:
            self.create_subscription(Image, camera_topic, self._on_image, camera_qos)
        if AIMDK:
            self.vad = AimdkVadAssembler()
            audio_qos = QoSProfile(reliability=ReliabilityPolicy.BEST_EFFORT, history=HistoryPolicy.KEEP_LAST, depth=500)
            self.create_subscription(ProcessedAudioOutput, audio_topic, self._on_audio, audio_qos)
        else:
            self.get_logger().warning("aimdk_msgs no está disponible: voz y TTS deshabilitados.")
        self.get_logger().info(f"Cámara: {camera_topic} · Audio: {audio_topic} · Backend: {backend_url}")

    # ---------- callbacks (no bloquean: delegan en hilos) ----------

    def _push(self, frame) -> None:
        if frame is not None:
            if self.rotate:
                import cv2

                frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
            self.frames.push(frame)

    def _on_compressed(self, msg: CompressedImage) -> None:
        self._push(decode_jpeg(bytes(msg.data)))

    def _on_image(self, msg: Image) -> None:
        if msg.encoding.lower() == "rgb8":
            self._push(rgb8_to_bgr(bytes(msg.data), msg.width, msg.height, msg.step))

    def _on_audio(self, msg) -> None:
        state = msg.audio_vad_state.value
        self.agent.on_mic_state({VAD_BEGIN: "escuchando", VAD_PROCESSING: "escuchando",
                                 VAD_END: "procesando"}.get(state, "silencio"))
        utterance = self.vad.feed(state, bytes(msg.audio_data))
        if utterance:
            threading.Thread(target=self.agent.on_utterance, args=(utterance,), daemon=True).start()

    def _vision_loop(self) -> None:
        for frame in self.frames.frames():
            try:
                self.agent.on_frame(frame)
            except Exception as error:  # un fotograma defectuoso no detiene el agente
                self.get_logger().error(f"Error de visión: {error}")
                time.sleep(0.5)

    def destroy_node(self):
        self.heartbeat.stop()
        self.frames.close()
        self.agent.end_session()
        return super().destroy_node()


def main() -> None:
    rclpy.init()
    node = ReceptionAgentNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
