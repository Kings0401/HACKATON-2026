"""Toma una foto de cada cámara del X2 para identificar cuál es cuál.

    python3 camaras.py          # guarda ~/nclub/capturas/<camara>.jpg e imprime un resumen

No mueve el robot: solo se suscribe unos segundos a cada topic de imagen.
"""

import time
from pathlib import Path

import rclpy
from rclpy.node import Node
from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import CompressedImage

OUT = Path.home() / "nclub" / "capturas"


class Probe(Node):
    def __init__(self):
        super().__init__("nclub_camera_probe")
        self.stats = {}

    def topics(self):
        deadline = time.time() + 6
        found = []
        while time.time() < deadline:
            found = sorted(
                name for name, types in self.get_topic_names_and_types()
                if "sensor_msgs/msg/CompressedImage" in types and "depth" not in name and "h265" not in name
            )
            if found:
                break
            rclpy.spin_once(self, timeout_sec=0.5)
        return found

    def sample(self, topic, seconds=3.0):
        info = {"count": 0, "saved": None, "format": ""}
        name = topic.strip("/").replace("aima/hal/sensor/", "").replace("/rgb_image/compressed", "").replace("/", "_")

        def on_image(msg):
            info["count"] += 1
            info["format"] = msg.format
            data = bytes(msg.data)
            if info["saved"] is None and info["count"] >= 3 and data.rstrip(b"\x00").endswith(b"\xff\xd9"):
                path = OUT / f"{name}.jpg"
                path.write_bytes(data)
                info["saved"] = path

        qos = QoSProfile(reliability=ReliabilityPolicy.BEST_EFFORT, history=HistoryPolicy.KEEP_LAST, depth=5)
        sub = self.create_subscription(CompressedImage, topic, on_image, qos)
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
    print(f"{name:<32} {hz:5.1f} fps  foto={'si' if info['saved'] else 'no'}  topic={topic}")
node.destroy_node()
rclpy.shutdown()
