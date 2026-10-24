"""Toma una foto de cada cámara del X2 para identificar cuál es cuál.

    python3 camaras.py          # guarda ~/nclub/capturas/<camara>.jpg e imprime un resumen

No mueve el robot: solo se suscribe unos segundos a cada topic de imagen.
"""

import time
from pathlib import Path

import rclpy
from rclpy.node import Node
from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import CompressedImage, Image

OUT = Path.home() / "nclub" / "capturas"
# Cámara elegida por N Club: puede publicarse solo sin comprimir (sensor_msgs/Image).
CENTER = "/aima/hal/sensor/rgb_head_front_center/rgb_image"


class Probe(Node):
    def __init__(self):
        super().__init__("nclub_camera_probe")
        self.stats = {}

    def topics(self):
        deadline = time.time() + 6
        found = []
        while time.time() < deadline:
            listed = self.get_topic_names_and_types()
            found = sorted(
                name for name, types in listed
                if "sensor_msgs/msg/CompressedImage" in types and "depth" not in name and "h265" not in name
            )
            if any(name == CENTER for name, _ in listed) and f"{CENTER}/compressed" not in found:
                found.append(CENTER)
            if found:
                break
            rclpy.spin_once(self, timeout_sec=0.5)
        return found

    def sample(self, topic, seconds=3.0):
        info = {"count": 0, "saved": None, "format": ""}
        name = topic.strip("/").replace("aima/hal/sensor/", "").replace("/rgb_image/compressed", "")
        name = name.replace("/rgb_image", "").replace("/", "_")

        def on_raw(msg):
            info["count"] += 1
            info["format"] = msg.encoding
            if info["saved"] is None and info["count"] >= 3 and msg.encoding.lower() in ("rgb8", "bgr8"):
                import cv2
                import numpy as np

                arr = np.frombuffer(bytes(msg.data), np.uint8).reshape(msg.height, msg.step)[:, : msg.width * 3]
                arr = arr.reshape(msg.height, msg.width, 3)
                if msg.encoding.lower() == "rgb8":
                    arr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
                path = OUT / f"{name}.jpg"
                cv2.imwrite(str(path), arr)
                info["saved"] = path

        def on_image(msg):
            info["count"] += 1
            info["format"] = msg.format
            data = bytes(msg.data)
            if info["saved"] is None and info["count"] >= 3 and data.rstrip(b"\x00").endswith(b"\xff\xd9"):
                path = OUT / f"{name}.jpg"
                path.write_bytes(data)
                info["saved"] = path

        qos = QoSProfile(reliability=ReliabilityPolicy.BEST_EFFORT, history=HistoryPolicy.KEEP_LAST, depth=5)
        raw = not topic.endswith("/compressed")
        sub = self.create_subscription(Image if raw else CompressedImage, topic, on_raw if raw else on_image, qos)
        end = time.time() + seconds
        while time.time() < end:
            rclpy.spin_once(self, timeout_sec=0.05)
        self.destroy_subscription(sub)
        return name, info


OUT.mkdir(parents=True, exist_ok=True)
for old in OUT.glob("*.jpg"):
    old.unlink()
rclpy.init()
node = Probe()
topics = node.topics()
print(f"CAMARAS={len(topics)}")
for topic in topics:
    name, info = node.sample(topic)
    hz = info["count"] / 3.0
    print(f"{name:<32} {hz:5.1f} fps  foto={'si' if info['saved'] else 'no'}  {info['format']:<6} topic={topic}")
node.destroy_node()
rclpy.shutdown()
