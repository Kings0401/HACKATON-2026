#!/usr/bin/env bash
# Inicia el agente N Club del Booster K1 en segundo plano (registro en ~/nclub/logs/k1.log).
NCLUB="$HOME/nclub"
cd "$NCLUB" || exit 1
set -a
. "$NCLUB/k1.env"
set +a
source /opt/ros/humble/setup.bash
export PYTHONPATH="$NCLUB/robot_agent:$NCLUB/vision:$PYTHONPATH"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"  # PulseAudio del usuario
export NCLUB_REGISTRO_DIR="$NCLUB/dataset/registro"
VOZ="$NCLUB/voces/${NCLUB_PIPER_VOICE:-es_MX-claude-high}.onnx"
[ -s "$VOZ" ] && export NCLUB_PIPER_MODEL="$VOZ"
export NCLUB_FIRMWARE="$(grep -oE 'Version: [^ ]+' /opt/booster/version.txt 2>/dev/null | tail -1 | cut -d' ' -f2)"

bash "$NCLUB/stop_k1.sh" >/dev/null 2>&1
mkdir -p logs
setsid nohup "$NCLUB/.venv/bin/python" -m nclub_agent.k1_node >"$NCLUB/logs/k1.log" 2>&1 < /dev/null &
echo $! >"$NCLUB/k1.pid"
sleep 12
if kill -0 "$(cat "$NCLUB/k1.pid")" 2>/dev/null; then
  echo "AGENTE-K1-INICIADO pid=$(cat "$NCLUB/k1.pid")"
  grep -E "facial|Voz|Micrófono|activo|Saludo|ERROR|Error|AVISO" "$NCLUB/logs/k1.log" | tail -8
else
  echo "AGENTE-K1-FALLO"; tail -30 "$NCLUB/logs/k1.log"; exit 1
fi
