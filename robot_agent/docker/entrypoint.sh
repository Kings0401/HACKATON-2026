#!/usr/bin/env bash
# Compila aimdk_msgs desde el SDK montado (si existe) y el paquete del agente.
set -e
source /opt/ros/humble/setup.bash
if [ -d /sdk ]; then
  msgs=$(find /sdk -name package.xml -path "*aimdk_msgs*" -printf '%h\n' | head -n 1)
  if [ -n "$msgs" ] && [ ! -e /ws/src/aimdk_msgs ]; then
    ln -s "$msgs" /ws/src/aimdk_msgs
  fi
else
  echo "AVISO: /sdk no montado; el agente funcionará sin audio ni TTS (aimdk_msgs ausente)."
fi
cd /ws
colcon build --symlink-install >/tmp/colcon.log 2>&1 || { cat /tmp/colcon.log; exit 1; }
source /ws/install/setup.bash
exec "$@"
