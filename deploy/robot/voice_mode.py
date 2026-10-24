"""Cambia el modo del sistema de interacción del X2 (AimDK, sección 8.1).

    python3 voice_mode.py only_voice   # el robot escucha sin palabra de activación
    python3 voice_mode.py normal       # vuelve al asistente integrado

Después hay que reiniciar el agente integrado (lo hace voice_mode.sh).
"""

import sys
import time

import rclpy
from aimdk_msgs.msg import AgentPropertiesValue
from aimdk_msgs.srv import SetAgentPropertiesRequest
from rclpy.node import Node

RUN_MODE = 0x02  # AGENT_PROPERTY_RUN_MODE

mode = sys.argv[1] if len(sys.argv) > 1 else "only_voice"
if mode not in ("only_voice", "normal"):
    raise SystemExit("Modo no válido: use only_voice o normal")
rclpy.init()
node = Node("nclub_voice_mode")
client = node.create_client(SetAgentPropertiesRequest, "/aimdk_5Fmsgs/srv/SetAgentPropertiesRequest")
if not client.wait_for_service(timeout_sec=8.0):
    raise SystemExit("Servicio SetAgentPropertiesRequest no disponible")
req = SetAgentPropertiesRequest.Request()
prop = AgentPropertiesValue()
prop.key.value = RUN_MODE
prop.value = mode
req.contents.properties = [prop]
response = None
for _ in range(8):  # el ejemplo oficial reintenta: el par remoto responde tarde
    req.header.header.stamp = node.get_clock().now().to_msg()
    future = client.call_async(req)
    rclpy.spin_until_future_complete(node, future, timeout_sec=0.5)
    if future.done():
        response = future.result()
        break
    time.sleep(0.2)
status = getattr(getattr(getattr(response, "header", None), "status", None), "value", None)
print(f"MODO={mode} estado={status} mensaje={getattr(getattr(response, 'header', None), 'message', '')}")
node.destroy_node()
rclpy.shutdown()
raise SystemExit(0 if status == 1 else 1)
