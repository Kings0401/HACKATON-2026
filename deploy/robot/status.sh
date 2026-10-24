#!/usr/bin/env bash
# Estado del agente y últimas líneas del registro.
NCLUB="$HOME/nclub"
if [ -f "$NCLUB/agent.pid" ] && kill -0 "$(cat "$NCLUB/agent.pid")" 2>/dev/null; then
  echo "EN EJECUCION pid=$(cat "$NCLUB/agent.pid")"
else
  echo "DETENIDO"
fi
echo "Fotos registradas: $(find "$NCLUB/dataset/registro" -type f 2>/dev/null | wc -l)"
grep -v "Warning\]" "$NCLUB/logs/agent.log" 2>/dev/null | tail -${1:-15}
