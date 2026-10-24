"""ros2 launch nclub_agent agent.launch.py [params:=/ruta/x2_ultra.yaml]"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    default = os.path.join(get_package_share_directory("nclub_agent"), "config", "x2_ultra.yaml")
    return LaunchDescription([
        DeclareLaunchArgument("params", default_value=default),
        Node(
            package="nclub_agent",
            executable="reception_agent",
            name="nclub_reception_agent",
            parameters=[LaunchConfiguration("params")],
            output="screen",
            respawn=True,  # reconexión ante caídas del proceso
            respawn_delay=3.0,
        ),
    ])
