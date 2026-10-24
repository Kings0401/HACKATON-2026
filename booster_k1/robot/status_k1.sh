#!/usr/bin/env bash
# Estado del agente K1 y últimas líneas del registro.
NCLUB="$HOME/nclub"
if [ -f "$NCLUB/k1.pid" ] && kill -0 "$(cat "$NCLUB/k1.pid")" 2>/dev/null; then
  echo "EN EJECUCION pid=$(cat "$NCLUB/k1.pid")"
else
  echo "DETENIDO"
fi
echo "Fotos registradas: $(find "$NCLUB/dataset/registro" -type f 2>/dev/null | wc -l)"
tail -${1:-15} "$NCLUB/logs/k1.log" 2>/dev/null
