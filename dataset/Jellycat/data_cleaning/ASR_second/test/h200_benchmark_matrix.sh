#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

: "${RUN_DIR:=${SCRIPT_DIR}/runs/latest}"
if [[ -f "${RUN_DIR}/run_env.sh" ]]; then
  # shellcheck source=/dev/null
  source "${RUN_DIR}/run_env.sh"
fi

: "${PORTS:=8000,8001,8002,8003,8004,8005,8006,8007}"
: "${LIMITS:=100 1000}"
: "${WORKERS_PER_PORT_LIST:=1 2 4}"
: "${LANGS:=ZH EN}"
: "${TIMEOUT:=600}"
: "${MAX_RETRIES:=2}"
: "${INCLUDE_EDITS:=1}"


echo "run_dir=${RUN_DIR}"
echo "ports=${PORTS}"
echo "limits=${LIMITS}"
echo "workers_per_port_list=${WORKERS_PER_PORT_LIST}"

for limit in ${LIMITS}; do
  for wpp in ${WORKERS_PER_PORT_LIST}; do
    label="limit${limit}_wpp${wpp}"
    echo "== Matrix item ${label} =="
    RUN_DIR="${RUN_DIR}" \
    PORTS="${PORTS}" \
    LIMIT="${limit}" \
    LANGS="${LANGS}" \
    WORKERS_PER_PORT="${wpp}" \
    TIMEOUT="${TIMEOUT}" \
    MAX_RETRIES="${MAX_RETRIES}" \
    INCLUDE_EDITS="${INCLUDE_EDITS}" \
    LABEL="${label}" \
      bash "${SCRIPT_DIR}/h200_run_benchmark.sh"
  done
done
