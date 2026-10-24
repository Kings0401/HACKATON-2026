#!/usr/bin/env bash
# Uso: bash voice_mode.sh only_voice|normal  (cambia el modo y reinicia el agente integrado)
set -e
source /opt/ros/humble/setup.bash
source "$HOME/aimdk/install/local_setup.bash"
python3 "$HOME/nclub/voice_mode.py" "${1:-only_voice}"
aima em stop-app agent
aima em start-app agent
echo "MODO-VOZ-APLICADO ${1:-only_voice}"
