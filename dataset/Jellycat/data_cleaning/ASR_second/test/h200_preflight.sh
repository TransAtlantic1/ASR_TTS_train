#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ASR_DIR=$(cd "${SCRIPT_DIR}/.." && pwd)
WORKSPACE_ROOT=$(cd "${ASR_DIR}/../.." && pwd)

: "${ASR_ENV:=meanaudio2}"
: "${MODEL_PATH:=${WORKSPACE_ROOT}/model/Qwen3-ASR-1.7B}"
: "${AUDIO_ROOT:=/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat}"
: "${ZH_MANIFEST:=${AUDIO_ROOT}/manifests/ZH/jellycat_ZH_segments.jsonl.gz}"
: "${EN_MANIFEST:=${AUDIO_ROOT}/manifests/EN/jellycat_EN_segments.jsonl.gz}"
: "${H200_GPUS:=0,1,2,3,4,5,6,7}"
: "${PORTS:=8000,8001,8002,8003,8004,8005,8006,8007}"
: "${RUN_ID:=preflight_$(date -u '+%Y%m%d-%H%M%S')}"
: "${RUN_DIR:=${SCRIPT_DIR}/runs/${RUN_ID}}"

mkdir -p "${RUN_DIR}"
exec > >(tee -a "${RUN_DIR}/preflight.log") 2>&1

split_list() {
  local input="${1//,/ }"
  local -n output="$2"
  read -r -a output <<< "${input}"
}

port_in_use() {
  local port="$1"
  ss -ltn 2>/dev/null | awk '{print $4}' | grep -Eq "[:.]${port}$"
}

echo "run_dir=${RUN_DIR}"
echo "workspace=${WORKSPACE_ROOT}"
echo "asr_env=${ASR_ENV}"
echo "model_path=${MODEL_PATH}"
echo "audio_root=${AUDIO_ROOT}"
echo "zh_manifest=${ZH_MANIFEST}"
echo "en_manifest=${EN_MANIFEST}"

[[ -d "${MODEL_PATH}" ]] || { echo "missing model path: ${MODEL_PATH}" >&2; exit 2; }
[[ -f "${ZH_MANIFEST}" ]] || { echo "missing ZH manifest: ${ZH_MANIFEST}" >&2; exit 2; }
[[ -f "${EN_MANIFEST}" ]] || { echo "missing EN manifest: ${EN_MANIFEST}" >&2; exit 2; }
[[ -f "${ASR_DIR}/verify_edit_data.py" ]] || { echo "missing verify_edit_data.py" >&2; exit 2; }

command -v conda >/dev/null 2>&1 || { echo "conda not found" >&2; exit 2; }
command -v nvidia-smi >/dev/null 2>&1 || { echo "nvidia-smi not found" >&2; exit 2; }

echo
echo "== GPU snapshot =="
nvidia-smi --query-gpu=index,name,memory.total,memory.used,utilization.gpu --format=csv | tee "${RUN_DIR}/gpu_snapshot.csv"

split_list "${H200_GPUS}" GPU_LIST
split_list "${PORTS}" PORT_LIST
if [[ ${#GPU_LIST[@]} -ne ${#PORT_LIST[@]} ]]; then
  echo "H200_GPUS and PORTS counts differ: ${#GPU_LIST[@]} vs ${#PORT_LIST[@]}" >&2
  exit 2
fi

echo
echo "== Port check =="
for port in "${PORT_LIST[@]}"; do
  if port_in_use "${port}"; then
    echo "port ${port}: in use" >&2
    exit 2
  fi
  echo "port ${port}: free"
done

echo
echo "== Conda command check =="
conda run -n "${ASR_ENV}" bash -lc 'command -v qwen-asr-serve'

echo
echo "== Python dependency check =="
conda run -n "${ASR_ENV}" python - <<'PY'
import importlib.util
mods = ["requests", "jiwer", "pypinyin", "qwen_asr", "opencc", "zhconv", "tqdm", "torch", "vllm"]
for mod in mods:
    print(f"{mod}={importlib.util.find_spec(mod) is not None}")
PY

echo
echo "== Manifest dry-runs =="
conda run -n "${ASR_ENV}" python "${ASR_DIR}/verify_edit_data.py" \
  --dry-run \
  --manifest "${ZH_MANIFEST}" \
  --limit 1 \
  --audio_root "${AUDIO_ROOT}" \
  --ports "${PORTS}"

conda run -n "${ASR_ENV}" python "${ASR_DIR}/verify_edit_data.py" \
  --dry-run \
  --manifest "${EN_MANIFEST}" \
  --limit 1 \
  --audio_root "${AUDIO_ROOT}" \
  --ports "${PORTS}"

echo "preflight=ok" | tee "${RUN_DIR}/preflight.status"
