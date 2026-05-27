#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
: "${RUN_DIR:=${SCRIPT_DIR}/runs/latest}"
: "${INTERVAL:=5}"

mkdir -p "${RUN_DIR}"
OUT="${RUN_DIR}/gpu_monitor.csv"

if [[ ! -f "${OUT}" ]]; then
  echo "timestamp,index,name,utilization.gpu,memory.used,memory.total,power.draw" > "${OUT}"
fi

echo "Writing GPU monitor samples to ${OUT}; Ctrl+C to stop."
while true; do
  nvidia-smi --query-gpu=timestamp,index,name,utilization.gpu,memory.used,memory.total,power.draw \
    --format=csv,noheader,nounits >> "${OUT}"
  sleep "${INTERVAL}"
done
