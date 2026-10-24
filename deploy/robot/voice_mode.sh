#!/usr/bin/env bash
# Uso: bash voice_mode.sh only_voice|normal  (cambia el modo y reinicia el agente integrado)
set -e
source /opt/ros/humble/setup.bash
source "$HOME/aimdk/install/local_setup.bash"
python3 "$HOME/nclub/voice_mode.py" "${1:-only_voice}"
# El agente integrado corre en el computador de interacción (10.0.1.42), no aquí:
# el modo queda guardado y se aplica al reiniciar el robot (o su agente en 10.0.1.42).
echo "MODO-VOZ-GUARDADO ${1:-only_voice}: reinicie el robot para aplicarlo"
