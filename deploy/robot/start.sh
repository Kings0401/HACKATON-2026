#!/usr/bin/env bash
# Inicia el agente de recepción N Club en segundo plano (registro en ~/nclub/logs).
NCLUB="$HOME/nclub"
cd "$NCLUB" || exit 1
set -a
. "$NCLUB/robot.env"
set +a
source /opt/ros/humble/setup.bash
source "$HOME/aimdk/install/local_setup.bash" 2>/dev/null || echo "AVISO: SDK AimDK sin compilar (sin voz ni gestos)"
if [ -x .venv/bin/python ]; then PY="$NCLUB/.venv/bin/python"; else PY=python3; fi
export PYTHONPATH="$NCLUB/robot_agent:$NCLUB/vision:$PYTHONPATH"

bash "$NCLUB/stop.sh" >/dev/null 2>&1
mkdir -p logs
nohup "$PY" -m nclub_agent.ros_node --ros-args \
  --params-file "$NCLUB/robot_agent/config/x2_ultra.yaml" \
  -p backend_url:="$NCLUB_API_URL" \
  -p robot_id:="${NCLUB_ROBOT_ID:-robot1}" \
  -p camera:="${NCLUB_CAMERA:-frente}" \
  -p registro_dir:="$NCLUB/dataset/registro" \
  -p gestures_enabled:="${NCLUB_GESTURES:-false}" \
  -p asr_engine:="${NCLUB_ASR:-faster-whisper}" \
  -p asr_model:="${NCLUB_ASR_MODEL:-small}" \
  >"$NCLUB/logs/agent.log" 2>&1 &
echo $! >"$NCLUB/agent.pid"
sleep 8
if kill -0 "$(cat "$NCLUB/agent.pid")" 2>/dev/null; then
  echo "AGENTE-INICIADO pid=$(cat "$NCLUB/agent.pid")"
  grep -E "Galería|Cámara|Gestos|Backend|ERROR|Error" "$NCLUB/logs/agent.log" | grep -v "Warning\]" | tail -6
else
  echo "AGENTE-FALLO"; tail -30 "$NCLUB/logs/agent.log"; exit 1
fi
