#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ASR_DIR=$(cd "${SCRIPT_DIR}/.." && pwd)
WORKSPACE_ROOT=$(cd "${ASR_DIR}/../.." && pwd)

: "${ASR_ENV:=meanaudio2}"
: "${MODEL_PATH:=${WORKSPACE_ROOT}/model/Qwen3-ASR-1.7B}"
: "${H200_GPUS:=0,1,2,3,4,5,6,7}"
: "${PORTS:=8000,8001,8002,8003,8004,8005,8006,8007}"
: "${GPU_MEMORY_UTILIZATION:=0.85}"
: "${TENSOR_PARALLEL_SIZE:=1}"
: "${MAX_MODEL_LEN:=4096}"
: "${HOST:=127.0.0.1}"
: "${READY_TIMEOUT:=1800}"
: "${RUN_ID:=$(date -u '+%Y%m%d-%H%M%S')}"
: "${CACHE_ROOT:=/tmp/qwen_asr_cache_${RUN_ID}}"
: "${VLLM_DISABLE_COMPILE_CACHE:=1}"
: "${RUN_DIR:=${SCRIPT_DIR}/runs/${RUN_ID}}"

mkdir -p "${RUN_DIR}/logs" "${RUN_DIR}/status" "${SCRIPT_DIR}/runs"
ln -sfn "${RUN_DIR}" "${SCRIPT_DIR}/runs/latest"
exec > >(tee -a "${RUN_DIR}/start.log") 2>&1

split_list() {
  local input="${1//,/ }"
  local -n output="$2"
  read -r -a output <<< "${input}"
}

port_in_use() {
  local port="$1"
  ss -ltn 2>/dev/null | awk '{print $4}' | grep -Eq "[:.]${port}$"
}

http_ready() {
  local port="$1"
  python3 - "${port}" <<'PY'
import sys
import urllib.error
import urllib.request

port = sys.argv[1]
try:
    urllib.request.urlopen(f"http://127.0.0.1:{port}/v1/models", timeout=2)
    raise SystemExit(0)
except urllib.error.HTTPError:
    raise SystemExit(0)
except Exception:
    raise SystemExit(1)
PY
}

[[ -d "${MODEL_PATH}" ]] || { echo "missing model path: ${MODEL_PATH}" >&2; exit 2; }
command -v conda >/dev/null 2>&1 || { echo "conda not found" >&2; exit 2; }

split_list "${H200_GPUS}" GPU_LIST
split_list "${PORTS}" PORT_LIST

if [[ "${TENSOR_PARALLEL_SIZE}" != "1" ]]; then
  echo "This script is for 8 independent replicas with TENSOR_PARALLEL_SIZE=1." >&2
  exit 2
fi
if [[ ${#GPU_LIST[@]} -ne ${#PORT_LIST[@]} ]]; then
  echo "H200_GPUS count must equal PORTS count for replica mode." >&2
  echo "H200_GPUS=${H200_GPUS}" >&2
  echo "PORTS=${PORTS}" >&2
  exit 2
fi

for port in "${PORT_LIST[@]}"; do
  if port_in_use "${port}"; then
    echo "port ${port} is already in use; stop the old service or choose another port." >&2
    exit 2
  fi
done

cat > "${RUN_DIR}/run_env.sh" <<EOF
export RUN_ID="${RUN_ID}"
export RUN_DIR="${RUN_DIR}"
export ASR_ENV="${ASR_ENV}"
export MODEL_PATH="${MODEL_PATH}"
export H200_GPUS="${H200_GPUS}"
export PORTS="${PORTS}"
export GPU_MEMORY_UTILIZATION="${GPU_MEMORY_UTILIZATION}"
export TENSOR_PARALLEL_SIZE="${TENSOR_PARALLEL_SIZE}"
export MAX_MODEL_LEN="${MAX_MODEL_LEN}"
export HOST="${HOST}"
export CACHE_ROOT="${CACHE_ROOT}"
export VLLM_DISABLE_COMPILE_CACHE="${VLLM_DISABLE_COMPILE_CACHE}"
EOF

{
  echo -e "gpu\tport\tpid\tlog"
} > "${RUN_DIR}/service_pids.tsv"

echo "Starting ${#GPU_LIST[@]} Qwen3-ASR replicas"
echo "run_dir=${RUN_DIR}"
echo "model=${MODEL_PATH}"

for i in "${!GPU_LIST[@]}"; do
  gpu="${GPU_LIST[$i]}"
  port="${PORT_LIST[$i]}"
  log_file="${RUN_DIR}/logs/gpu${gpu}_port${port}.log"
  cache_dir="${CACHE_ROOT}/gpu${gpu}"
  mkdir -p "${cache_dir}/torchinductor" "${cache_dir}/triton" "${cache_dir}/torch_extensions" "${cache_dir}/vllm" "${cache_dir}/xdg"
  echo "launch gpu=${gpu} port=${port} log=${log_file} cache=${cache_dir}"
  env CUDA_VISIBLE_DEVICES="${gpu}" \
    TORCHINDUCTOR_CACHE_DIR="${cache_dir}/torchinductor" \
    TRITON_CACHE_DIR="${cache_dir}/triton" \
    TORCH_EXTENSIONS_DIR="${cache_dir}/torch_extensions" \
    VLLM_CACHE_ROOT="${cache_dir}/vllm" \
    VLLM_DISABLE_COMPILE_CACHE="${VLLM_DISABLE_COMPILE_CACHE}" \
    XDG_CACHE_HOME="${cache_dir}/xdg" \
    conda run -n "${ASR_ENV}" --no-capture-output qwen-asr-serve "${MODEL_PATH}" \
      --gpu-memory-utilization "${GPU_MEMORY_UTILIZATION}" \
      --host "${HOST}" \
      --port "${port}" \
      --tensor-parallel-size "${TENSOR_PARALLEL_SIZE}" \
      --max-model-len "${MAX_MODEL_LEN}" \
      > "${log_file}" 2>&1 &
  pid=$!
  echo -e "${gpu}\t${port}\t${pid}\t${log_file}" >> "${RUN_DIR}/service_pids.tsv"
done

echo "Waiting for ports to respond"
deadline=$((SECONDS + READY_TIMEOUT))
for i in "${!GPU_LIST[@]}"; do
  gpu="${GPU_LIST[$i]}"
  port="${PORT_LIST[$i]}"
  pid=$(awk -F '\t' -v p="${port}" '$2 == p {print $3}' "${RUN_DIR}/service_pids.tsv")
  ready=0
  while (( SECONDS < deadline )); do
    if http_ready "${port}"; then
      ready=1
      break
    fi
    if ! kill -0 "${pid}" 2>/dev/null; then
      echo "service died before ready: gpu=${gpu} port=${port} pid=${pid}" >&2
      tail -n 80 "${RUN_DIR}/logs/gpu${gpu}_port${port}.log" >&2 || true
      exit 1
    fi
    sleep 5
  done
  if [[ "${ready}" != "1" ]]; then
    echo "timeout waiting for port ${port}" >&2
    tail -n 80 "${RUN_DIR}/logs/gpu${gpu}_port${port}.log" >&2 || true
    exit 1
  fi
  echo "ready gpu=${gpu} port=${port}"
done

echo "services=ready" | tee "${RUN_DIR}/status/services.ready"
echo "Use RUN_DIR=${RUN_DIR} for benchmarks and stop script."
