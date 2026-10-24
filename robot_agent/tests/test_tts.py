"""Revisión del habla del robot sin ROS: se simulan rclpy y aimdk_msgs para
comprobar que la petición PlayTts se arma como en el ejemplo oficial play_tts
y que el éxito o el error del servicio se interpretan bien."""

import sys
import threading
import time
import types
from pathlib import Path
from types import SimpleNamespace as NS

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT / "robot_agent", ROOT / "vision"):
    sys.path.insert(0, str(p))


def install_fake_ros():
    mods = {name: types.ModuleType(name) for name in (
        "rclpy", "rclpy.node", "rclpy.qos", "sensor_msgs", "sensor_msgs.msg",
        "aimdk_msgs", "aimdk_msgs.msg", "aimdk_msgs.srv")}
    mods["rclpy.node"].Node = object
    for attr in ("HistoryPolicy", "QoSProfile", "ReliabilityPolicy"):
        setattr(mods["rclpy.qos"], attr, object)
    mods["sensor_msgs.msg"].CompressedImage = mods["sensor_msgs.msg"].Image = object

    class PlayTts:
        class Request:
            def __init__(self):
                self.header = NS(header=NS(stamp=None))
                self.tts_req = NS(text="", domain="", trace_id="", is_interrupted=False,
                                  priority_weight=-1, priority_level=NS(value=0))

    mods["aimdk_msgs.srv"].PlayTts = PlayTts
    mods["aimdk_msgs.msg"].TtsPriorityLevel = NS(INTERACTION_L6=6)
    mods["aimdk_msgs.msg"].ProcessedAudioOutput = object
    sys.modules.update(mods)


class FakeFuture:
    def __init__(self, response):
        self.response = response

    def done(self):
        return True

    def result(self):
        return self.response


class FakeClient:
    def __init__(self, response, ready=True):
        self.response, self.ready, self.requests = response, ready, []

    def wait_for_service(self, timeout_sec):
        return self.ready

    def service_is_ready(self):
        return self.ready

    def call_async(self, request):
        self.requests.append(request)
        return FakeFuture(self.response)


class FakeNode:
    def __init__(self, client):
        self.client, self.logs = client, []

    def create_client(self, srv, name):
        self.service = name
        return self.client

    def get_logger(self):
        node = self
        return NS(info=lambda m: node.logs.append(("info", m)), warning=lambda m: node.logs.append(("warn", m)),
                  error=lambda m: node.logs.append(("error", m)))

    def get_clock(self):
        return NS(now=lambda: NS(to_msg=lambda: "stamp"))


def speaker_for(response, ready=True):
    install_fake_ros()
    sys.modules.pop("nclub_agent.ros_node", None)
    from nclub_agent.ros_node import AimdkTtsSpeaker

    client = FakeClient(response, ready)
    node = FakeNode(client)
    return AimdkTtsSpeaker(node, "/aimdk_5Fmsgs/srv/PlayTts", attempts=2, wait_s=0), client, node


def wait_results(speaker, n=1):
    deadline = time.time() + 5
    while len(speaker.results) < n and time.time() < deadline:
        time.sleep(0.02)


def test_request_matches_official_play_tts_example():
    speaker, client, node = speaker_for(NS(tts_resp=NS(is_success=True)))
    speaker.speak("Bienvenida, Valeria. Su destino es el VIP Lounge.")
    wait_results(speaker)
    req = client.requests[0]
    assert node.service == "/aimdk_5Fmsgs/srv/PlayTts"
    assert req.tts_req.text.startswith("Bienvenida")
    assert req.tts_req.domain and req.tts_req.trace_id.startswith("nclub-")
    assert req.tts_req.is_interrupted is True and req.tts_req.priority_weight == 0
    assert req.tts_req.priority_level.value == 6  # INTERACTION_L6
    assert req.header.header.stamp == "stamp"
    assert speaker.results[0][1] is True


def test_service_error_is_reported():
    speaker, _, node = speaker_for(NS(tts_resp=NS(is_success=False, error_code=3, error_message="busy")))
    speaker.speak("Hola")
    wait_results(speaker)
    assert speaker.results[0] == (speaker.results[0][0], False, "3: busy")
    assert any(level == "error" for level, _ in node.logs)


def test_unavailable_service_retries_and_gives_up():
    speaker, client, _ = speaker_for(None, ready=False)
    speaker.speak("Hola")
    wait_results(speaker)
    assert client.requests == [] and speaker.results[0][2] == "servicio no disponible"


def test_speaking_does_not_block_the_caller():
    speaker, _, _ = speaker_for(NS(tts_resp=NS(is_success=True)))
    start = time.time()
    speaker.speak("Hola")
    assert time.time() - start < 0.2
    wait_results(speaker)
    assert threading.active_count() >= 1
