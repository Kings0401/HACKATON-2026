#!/usr/bin/env bash
# Detiene el agente de recepción N Club.
PID_FILE="$HOME/nclub/agent.pid"
if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  kill "$(cat "$PID_FILE")" && sleep 2
  kill -9 "$(cat "$PID_FILE")" 2>/dev/null
  echo "AGENTE-DETENIDO"
else
  echo "El agente no estaba en ejecución"
fi
rm -f "$PID_FILE"
