#!/usr/bin/env bash
# Instala dependencias del agente N Club en el computador de desarrollo del X2.
# Lo ejecuta desplegar_robot.ps1; puede repetirse sin daño.
set -eo pipefail
NCLUB="$HOME/nclub"
cd "$NCLUB"
mkdir -p logs dataset/registro
source /opt/ros/humble/setup.bash

echo "[1/5] Entorno de Python (con acceso a ROS 2 del sistema)"
if [ ! -x .venv/bin/python ]; then
  if ! python3 -m venv --system-site-packages .venv 2>/dev/null; then
    echo "  python3-venv no está disponible; se instala en el usuario (pip --user)"
    rm -rf .venv
  fi
fi
if [ -x .venv/bin/python ]; then PY="$NCLUB/.venv/bin/python"; PIPUSER=""; else PY=python3; PIPUSER="--user"; fi
"$PY" -m pip install $PIPUSER -q --upgrade pip || true

echo "[2/5] Visión y cliente HTTP (numpy<2 para no romper ROS Humble)"
printf 'numpy<2\n' > constraints.txt
"$PY" -m pip install $PIPUSER -q -c constraints.txt "numpy<2" "opencv-python-headless==4.10.0.84" "httpx>=0.27" "python-dotenv>=1.0"
"$PY" -m pip install $PIPUSER -q --no-deps -e vision

echo "[3/5] Reconocimiento de voz en español (faster-whisper, offline)"
if [ "${NCLUB_ASR:-faster-whisper}" = "faster-whisper" ]; then
  "$PY" -m pip install $PIPUSER -q -c constraints.txt "faster-whisper>=1.0" \
    && "$PY" -c "from faster_whisper import WhisperModel; WhisperModel('${NCLUB_ASR_MODEL:-small}', device='cpu', compute_type='int8'); print('  modelo de voz listo')" \
    || echo "  AVISO: faster-whisper no quedó disponible; el robot oirá pero no transcribirá"
fi

echo "[4/5] Mensajes del SDK AimDK (voz, micrófono y gestos)"
if [ ! -f "$HOME/aimdk/install/local_setup.bash" ] || [ ! -d "$HOME/aimdk/install/aimdk_msgs" ]; then
  (cd "$HOME/aimdk" && colcon build --packages-select aimdk_msgs py_examples)
fi

echo "[5/5] Modelos de rostro verificados (SHA-256)"
"$PY" -m nclub_vision.models

echo "INSTALACION-OK"
