#!/usr/bin/env bash
# Instala el agente N Club en el Booster K1. Lo ejecuta desplegar_k1.ps1; puede repetirse sin daño.
# No toca el Python del sistema: todo va en ~/nclub/.venv (con acceso a ROS 2, OpenCV y el SDK de Booster).
set -eo pipefail
NCLUB="$HOME/nclub"
cd "$NCLUB"
mkdir -p logs dataset/registro voces
source /opt/ros/humble/setup.bash

echo "[1/5] Entorno de Python aislado (ve los paquetes del sistema, no los modifica)"
[ -x .venv/bin/python ] || python3 -m venv --system-site-packages .venv
PY="$NCLUB/.venv/bin/python"
"$PY" -m pip install -q --upgrade pip
# numpy y OpenCV del sistema (1.26 y 4.11) se conservan; el SDK de Booster no se actualiza.
printf 'numpy<2\nbooster_robotics_sdk_python==1.5.6\n' > constraints.txt

echo "[2/5] Cliente HTTP y visión"
"$PY" -m pip install -q -c constraints.txt "httpx>=0.27" "python-dotenv>=1.0"

echo "[3/5] Reconocimiento de voz en español (faster-whisper, offline)"
if [ "${NCLUB_ASR:-faster-whisper}" = "faster-whisper" ]; then
  "$PY" -m pip install -q -c constraints.txt "faster-whisper>=1.0" \
    && "$PY" -c "from faster_whisper import WhisperModel; WhisperModel('${NCLUB_ASR_MODEL:-small}', device='cpu', compute_type='int8'); print('  modelo de voz listo')" \
    || echo "  AVISO: faster-whisper no quedó disponible; el robot oirá pero no transcribirá"
fi

echo "[4/5] Voz del robot en español (Piper, offline)"
VOZ="${NCLUB_PIPER_VOICE:-es_MX-claude-high}"
BASE="https://huggingface.co/rhasspy/piper-voices/resolve/main/es/${VOZ%%-*}/$(echo "$VOZ" | cut -d- -f2)/$(echo "$VOZ" | cut -d- -f3)"
if "$PY" -m pip install -q -c constraints.txt "piper-tts>=1.2"; then
  for ext in onnx onnx.json; do
    [ -s "voces/$VOZ.$ext" ] || curl -sfL -o "voces/$VOZ.$ext" "$BASE/$VOZ.$ext"
  done
  [ -s "voces/$VOZ.onnx" ] && echo "  voz $VOZ lista" || echo "  AVISO: no se descargó la voz; se usará espeak-ng"
else
  echo "  AVISO: piper-tts no se instaló; se usará espeak-ng"
fi

echo "[5/5] Modelos de rostro verificados (SHA-256)"
PYTHONPATH="$NCLUB/vision" "$PY" -m nclub_vision.models

echo "INSTALACION-OK"
