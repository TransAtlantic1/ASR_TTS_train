#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
: "${RUN_DIR:=${1:-${SCRIPT_DIR}/runs/latest}}"

if [[ ! -f "${RUN_DIR}/service_pids.tsv" ]]; then
  echo "missing service_pids.tsv under RUN_DIR=${RUN_DIR}" >&2
  exit 2
fi

mkdir -p "${RUN_DIR}/status"
exec > >(tee -a "${RUN_DIR}/stop.log") 2>&1

echo "Stopping services from ${RUN_DIR}/service_pids.tsv"

tail -n +2 "${RUN_DIR}/service_pids.tsv" | while IFS=$'\t' read -r gpu port pid log_file; do
  [[ -n "${pid}" ]] || continue
  if kill -0 "${pid}" 2>/dev/null; then
    echo "TERM gpu=${gpu} port=${port} pid=${pid}"
    pkill -TERM -P "${pid}" 2>/dev/null || true
    kill -TERM "${pid}" 2>/dev/null || true
  else
    echo "already stopped gpu=${gpu} port=${port} pid=${pid}"
  fi
done

sleep 5

tail -n +2 "${RUN_DIR}/service_pids.tsv" | while IFS=$'\t' read -r gpu port pid log_file; do
  [[ -n "${pid}" ]] || continue
  if kill -0 "${pid}" 2>/dev/null; then
    echo "KILL gpu=${gpu} port=${port} pid=${pid}"
    pkill -KILL -P "${pid}" 2>/dev/null || true
    kill -KILL "${pid}" 2>/dev/null || true
  fi
done

echo "services=stopped" | tee "${RUN_DIR}/status/services.stopped"
