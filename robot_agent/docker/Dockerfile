# Imagen de desarrollo del agente (Ubuntu 22.04 + ROS 2 Humble).
# Úsela en el PC host (modo "Host PC + cross-device networking") o adáptela al
# contenedor de desarrollo oficial de AimDK (obligatorio desde AimDK 1.2.0 en
# el computador del robot). aimdk_msgs NO se descarga aquí: se compila desde el
# SDK AimDK_X2 de la MISMA versión que el firmware, montado en /sdk.
#
#   docker build -f robot_agent/docker/Dockerfile -t nclub-agent .
#   docker run --rm -it --network host -v /ruta/AimDK_X2:/sdk:ro \
#     -v /ruta/dataset:/data/nclub/dataset:ro -e NCLUB_ROBOT_KEY=... nclub-agent
FROM ros:humble-ros-base-jammy

RUN apt-get update && apt-get install -y --no-install-recommends \
      python3-pip python3-opencv python3-numpy python3-colcon-common-extensions \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /ws
COPY vision /ws/vision
COPY robot_agent /ws/src/nclub_agent
COPY shared /ws/shared
RUN pip3 install --no-cache-dir "httpx>=0.27" "python-dotenv>=1.0" \
    && pip3 install --no-cache-dir --no-deps -e /ws/vision \
    && pip3 install --no-cache-dir "faster-whisper>=1.0" || echo "faster-whisper opcional no instalado"

COPY robot_agent/docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
CMD ["ros2", "launch", "nclub_agent", "agent.launch.py"]
