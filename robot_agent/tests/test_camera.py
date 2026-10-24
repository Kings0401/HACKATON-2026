"""Elección de cámara por nombre con la lista de topics real del X2 (24-10-2026)."""

import sys

from test_tts import install_fake_ros

S = "/aima/hal/sensor"
REAL_X2 = [  # topics de imagen observados en el robot de N Club
    f"{S}/rgb_head_rear/rgb_image", f"{S}/rgb_head_rear/rgb_image/compressed", f"{S}/rgb_head_rear/rgb_image/h265",
    f"{S}/rgbd_head_front/depth_image", f"{S}/rgbd_head_front/rgb_image",
    f"{S}/rgbd_head_front/rgb_image/compressed", f"{S}/rgbd_head_front/rgb_image/h265",
    f"{S}/stereo_head_front_left/rgb_image", f"{S}/stereo_head_front_left/rgb_image/compressed",
    f"{S}/stereo_head_front_right/rgb_image/compressed",
]


def pick():
    install_fake_ros()
    sys.modules.pop("nclub_agent.ros_node", None)
    from nclub_agent.ros_node import camera_candidates

    return camera_candidates


def test_frente_prefers_interaction_camera_when_published():
    choose = pick()
    with_interaction = REAL_X2 + [f"{S}/rgb_head_front/rgb_image/compressed"]
    assert choose(with_interaction, "frente") == f"{S}/rgb_head_front/rgb_image/compressed"
    assert choose(REAL_X2 + [f"{S}/interaction_front/rgb_image/compressed"], "frente").endswith(
        "interaction_front/rgb_image/compressed")


def test_frente_on_current_firmware_uses_front_stereo_not_rgbd_or_h265():
    choose = pick()
    topic = choose(REAL_X2, "frente")
    assert topic == f"{S}/stereo_head_front_left/rgb_image/compressed"


def test_named_presets_and_explicit_topic():
    choose = pick()
    assert choose(REAL_X2, "rgbd") == f"{S}/rgbd_head_front/rgb_image/compressed"
    assert choose(REAL_X2, "trasera") == f"{S}/rgb_head_rear/rgb_image/compressed"
    assert choose(REAL_X2, "estereo") == f"{S}/stereo_head_front_left/rgb_image/compressed"
    assert choose(REAL_X2, "/mi/topic/compressed") == "/mi/topic/compressed"
    assert choose([], "rgbd") == f"{S}/rgbd_head_front/rgb_image/compressed"  # sin descubrimiento
