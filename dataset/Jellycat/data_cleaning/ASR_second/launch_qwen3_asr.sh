#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
WORKSPACE_ROOT=$(cd "${SCRIPT_DIR}/../.." && pwd)

: "${MODEL_PATH:=${WORKSPACE_ROOT}/model/Qwen3-ASR-1.7B}"
: "${ASR_ENV:=meanaudio2}"
: "${CUDA_VISIBLE_DEVICES:=0}"
: "${PORTS:=8000}"
: "${LOG_DIR:=${SCRIPT_DIR}/logs}"
: "${GPU_MEMORY_UTILIZATION:=0.85}"
: "${TENSOR_PARALLEL_SIZE:=1}"
: "${HOST:=0.0.0.0}"
: "${DRY_RUN:=0}"
: "${MAX_MODEL_LEN:=}"
: "${VLLM_EXTRA_ARGS:=}"

read -r -a GPU_LIST <<< "${CUDA_VISIBLE_DEVICES//,/ }"
read -r -a PORT_LIST <<< "${PORTS//,/ }"

if [[ ${#GPU_LIST[@]} -eq 0 || ${#PORT_LIST[@]} -eq 0 ]]; then
  echo "CUDA_VISIBLE_DEVICES and PORTS must not be empty" >&2
  exit 2
fi

if [[ "${TENSOR_PARALLEL_SIZE}" == "1" && ${#GPU_LIST[@]} -ne ${#PORT_LIST[@]} ]]; then
  echo "For TENSOR_PARALLEL_SIZE=1, CUDA_VISIBLE_DEVICES count must equal PORTS count." >&2
  echo "CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES}" >&2
  echo "PORTS=${PORTS}" >&2
  exit 2
fi

if [[ "${TENSOR_PARALLEL_SIZE}" != "1" && ${#PORT_LIST[@]} -ne 1 ]]; then
  echo "For TENSOR_PARALLEL_SIZE>1, use one port and pass the GPU group via CUDA_VISIBLE_DEVICES." >&2
  exit 2
fi

mkdir -p "${LOG_DIR}"

if command -v conda >/dev/null 2>&1; then
  RUNNER=(conda run -n "${ASR_ENV}" --no-capture-output qwen-asr-serve)
else
  echo "conda not found; falling back to qwen-asr-serve from the current environment" >&2
  RUNNER=(qwen-asr-serve)
fi

EXTRA_ARGS=()
if [[ -n "${MAX_MODEL_LEN}" ]]; then
  EXTRA_ARGS+=(--max-model-len "${MAX_MODEL_LEN}")
fi
if [[ -n "${VLLM_EXTRA_ARGS}" ]]; then
  read -r -a USER_EXTRA_ARGS <<< "${VLLM_EXTRA_ARGS}"
  EXTRA_ARGS+=("${USER_EXTRA_ARGS[@]}")
fi

if [[ "${TENSOR_PARALLEL_SIZE}" == "1" ]]; then
  for i in "${!PORT_LIST[@]}"; do
    gpu="${GPU_LIST[$i]}"
    port="${PORT_LIST[$i]}"
    log_file="${LOG_DIR}/gpu${gpu}_port${port}.log"
    echo "Launching qwen-asr-serve on CUDA_VISIBLE_DEVICES=${gpu}, port=${port}"
    echo "  model=${MODEL_PATH}"
    echo "  log=${log_file}"
    if [[ "${DRY_RUN}" == "1" ]]; then
      echo "DRY_RUN=1 env CUDA_VISIBLE_DEVICES=${gpu} ${RUNNER[*]} ${MODEL_PATH} --gpu-memory-utilization ${GPU_MEMORY_UTILIZATION} --host ${HOST} --port ${port} --tensor-parallel-size ${TENSOR_PARALLEL_SIZE} ${EXTRA_ARGS[*]}"
      continue
    fi
    env CUDA_VISIBLE_DEVICES="${gpu}" "${RUNNER[@]}" "${MODEL_PATH}" \
      --gpu-memory-utilization "${GPU_MEMORY_UTILIZATION}" \
      --host "${HOST}" \
      --port "${port}" \
      --tensor-parallel-size "${TENSOR_PARALLEL_SIZE}" \
      "${EXTRA_ARGS[@]}" \
      > "${log_file}" 2>&1 &
    echo "  pid=$!"
  done
else
  port="${PORT_LIST[0]}"
  log_file="${LOG_DIR}/tp${TENSOR_PARALLEL_SIZE}_port${port}.log"
  echo "Launching qwen-asr-serve on CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES}, port=${port}, tensor_parallel=${TENSOR_PARALLEL_SIZE}"
  echo "  model=${MODEL_PATH}"
  echo "  log=${log_file}"
  if [[ "${DRY_RUN}" == "1" ]]; then
    echo "DRY_RUN=1 env CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES} ${RUNNER[*]} ${MODEL_PATH} --gpu-memory-utilization ${GPU_MEMORY_UTILIZATION} --host ${HOST} --port ${port} --tensor-parallel-size ${TENSOR_PARALLEL_SIZE} ${EXTRA_ARGS[*]}"
    exit 0
  fi
  env CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES}" "${RUNNER[@]}" "${MODEL_PATH}" \
    --gpu-memory-utilization "${GPU_MEMORY_UTILIZATION}" \
    --host "${HOST}" \
    --port "${port}" \
    --tensor-parallel-size "${TENSOR_PARALLEL_SIZE}" \
    "${EXTRA_ARGS[@]}" \
    > "${log_file}" 2>&1 &
  echo "  pid=$!"
fi

if [[ "${DRY_RUN}" == "1" ]]; then
  exit 0
fi

echo "All requested Qwen3-ASR instances launched. Press Ctrl+C to stop waiting."
wait
