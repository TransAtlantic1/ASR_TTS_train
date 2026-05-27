#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ASR_DIR=$(cd "${SCRIPT_DIR}/.." && pwd)

: "${ASR_ENV:=Qwen-ASR}"
: "${AUDIO_ROOT:=/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat}"
: "${HYP_OUTPUT_ROOT:=/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/asr_hyp/qwen3_asr_1p7b}"
: "${EN_MANIFEST:=${AUDIO_ROOT}/manifests/EN/jellycat_EN_segments.jsonl.gz}"
: "${ZH_MANIFEST:=${AUDIO_ROOT}/manifests/ZH/jellycat_ZH_segments.jsonl.gz}"
: "${PORTS:=8000,8001,8002,8003,8004,8005,8006,8007}"
: "${WORKERS_PER_PORT:=24}"
: "${MAX_INFLIGHT:=768}"
: "${TIMEOUT:=600}"
: "${MAX_RETRIES:=2}"
: "${INCLUDE_EDITS:=1}"
: "${RUN_FAILED_RETRY:=1}"
: "${LANG_ORDER:=EN ZH}"
: "${RUN_ID:=$(date -u '+%Y%m%d-%H%M%S')}"
: "${FULL_RUN_DIR:=${SCRIPT_DIR}/runs/full_${RUN_ID}}"

export ASR_ENV AUDIO_ROOT HYP_OUTPUT_ROOT EN_MANIFEST ZH_MANIFEST
export PORTS WORKERS_PER_PORT MAX_INFLIGHT TIMEOUT MAX_RETRIES INCLUDE_EDITS
export RUN_FAILED_RETRY LANG_ORDER RUN_ID FULL_RUN_DIR

mkdir -p "${FULL_RUN_DIR}/logs" "${FULL_RUN_DIR}/status" "${FULL_RUN_DIR}/manifests" "${HYP_OUTPUT_ROOT}"

if [[ "${JELLYCAT_FULL_SERIAL_CHILD:-0}" != "1" ]]; then
  export JELLYCAT_FULL_SERIAL_CHILD=1
  nohup bash "$0" "$@" > "${FULL_RUN_DIR}/nohup.log" 2>&1 &
  pid=$!
  echo "${pid}" > "${FULL_RUN_DIR}/full_serial.pid"
  cat > "${FULL_RUN_DIR}/run_full_env.sh" <<EOF
export RUN_ID="${RUN_ID}"
export FULL_RUN_DIR="${FULL_RUN_DIR}"
export ASR_ENV="${ASR_ENV}"
export AUDIO_ROOT="${AUDIO_ROOT}"
export HYP_OUTPUT_ROOT="${HYP_OUTPUT_ROOT}"
export PORTS="${PORTS}"
export WORKERS_PER_PORT="${WORKERS_PER_PORT}"
export MAX_INFLIGHT="${MAX_INFLIGHT}"
export TIMEOUT="${TIMEOUT}"
export MAX_RETRIES="${MAX_RETRIES}"
export INCLUDE_EDITS="${INCLUDE_EDITS}"
export RUN_FAILED_RETRY="${RUN_FAILED_RETRY}"
export LANG_ORDER="${LANG_ORDER}"
EOF
  echo "full_serial=started"
  echo "pid=${pid}"
  echo "run_dir=${FULL_RUN_DIR}"
  echo "log=${FULL_RUN_DIR}/nohup.log"
  echo "tail -f ${FULL_RUN_DIR}/nohup.log"
  exit 0
fi

exec > >(tee -a "${FULL_RUN_DIR}/full_serial.log") 2>&1

split_ports() {
  local input="${1//,/ }"
  read -r -a PORT_LIST <<< "${input}"
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

check_inputs() {
  command -v conda >/dev/null 2>&1 || { echo "conda not found" >&2; exit 2; }
  [[ -d "${AUDIO_ROOT}" ]] || { echo "missing AUDIO_ROOT=${AUDIO_ROOT}" >&2; exit 2; }
  [[ -f "${EN_MANIFEST}" ]] || { echo "missing EN_MANIFEST=${EN_MANIFEST}" >&2; exit 2; }
  [[ -f "${ZH_MANIFEST}" ]] || { echo "missing ZH_MANIFEST=${ZH_MANIFEST}" >&2; exit 2; }
  split_ports "${PORTS}"
  for port in "${PORT_LIST[@]}"; do
    if ! http_ready "${port}"; then
      echo "ASR service is not ready on port ${port}; start H200 services first." >&2
      exit 2
    fi
  done
}

count_lines() {
  local path="$1"
  if [[ -f "${path}" ]]; then
    wc -l < "${path}" | tr -d ' '
  else
    echo 0
  fi
}

dedupe_failed_manifest() {
  local input="$1"
  local output="$2"
  python3 - "${input}" "${output}" <<'PY_DEDUPE'
import json
import sys
from pathlib import Path

src = Path(sys.argv[1])
dst = Path(sys.argv[2])
seen = set()
total = kept = bad = 0
with src.open("r", encoding="utf-8") as fin, dst.open("w", encoding="utf-8") as fout:
    for line in fin:
        total += 1
        try:
            rec = json.loads(line)
        except Exception:
            bad += 1
            continue
        rec_id = rec.get("id") or rec.get("task_id")
        if rec_id is None:
            bad += 1
            continue
        rec_id = str(rec_id)
        if rec_id in seen:
            continue
        seen.add(rec_id)
        fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
        kept += 1
print(json.dumps({"input": str(src), "output": str(dst), "lines": total, "unique": kept, "duplicates": total - kept - bad, "bad": bad}, ensure_ascii=False))
PY_DEDUPE
}

child_pid=""
cleanup() {
  if [[ -n "${child_pid}" ]] && kill -0 "${child_pid}" 2>/dev/null; then
    echo "Stopping child process pid=${child_pid}"
    kill -TERM "${child_pid}" 2>/dev/null || true
    wait "${child_pid}" 2>/dev/null || true
  fi
}
trap cleanup INT TERM

run_lang() {
  local lang="$1"
  local manifest output failed log_name lang_lower
  case "${lang}" in
    EN|en)
      lang="EN"
      lang_lower="en"
      manifest="${EN_MANIFEST}"
      output="${HYP_OUTPUT_ROOT}/en.full.jsonl"
      failed="${HYP_OUTPUT_ROOT}/en.failed.jsonl"
      log_name="en.full"
      ;;
    ZH|zh)
      lang="ZH"
      lang_lower="zh"
      manifest="${ZH_MANIFEST}"
      output="${HYP_OUTPUT_ROOT}/zh.full.jsonl"
      failed="${HYP_OUTPUT_ROOT}/zh.failed.jsonl"
      log_name="zh.full"
      ;;
    *)
      echo "unsupported language in LANG_ORDER: ${lang}" >&2
      exit 2
      ;;
  esac

  local edit_args=()
  if [[ "${INCLUDE_EDITS}" == "0" ]]; then
    edit_args+=(--no-edits)
  fi

  echo "== ${lang} full ASR start $(date -u '+%Y-%m-%dT%H:%M:%SZ') =="
  echo "manifest=${manifest}"
  echo "output=${output}"
  echo "failed=${failed}"
  echo "existing_output_lines=$(count_lines "${output}")"
  echo "existing_failed_lines=$(count_lines "${failed}")"

  (
    set -euo pipefail
    conda run -n "${ASR_ENV}" --no-capture-output python "${ASR_DIR}/verify_edit_data.py" \
      --manifest "${manifest}" \
      --audio_root "${AUDIO_ROOT}" \
      --ports "${PORTS}" \
      --workers-per-port "${WORKERS_PER_PORT}" \
      --max-inflight "${MAX_INFLIGHT}" \
      --timeout "${TIMEOUT}" \
      --max-retries "${MAX_RETRIES}" \
      --output "${output}" \
      --failed-output "${failed}" \
      "${edit_args[@]}"
  ) > >(tee -a "${FULL_RUN_DIR}/logs/${log_name}.log") 2>&1 &
  child_pid=$!
  wait "${child_pid}"
  child_pid=""

  echo "== ${lang} full ASR done $(date -u '+%Y-%m-%dT%H:%M:%SZ') =="
  echo "output_lines=$(count_lines "${output}")"
  echo "failed_lines=$(count_lines "${failed}")"
  echo "${lang}=done" > "${FULL_RUN_DIR}/status/${lang}.done"

  if [[ "${RUN_FAILED_RETRY}" == "1" && -s "${failed}" ]]; then
    local retry_manifest retry_output retry_failed retry_log_name
    retry_manifest="${FULL_RUN_DIR}/manifests/${lang_lower}.failed.unique.jsonl"
    retry_output="${HYP_OUTPUT_ROOT}/${lang_lower}.retry_${RUN_ID}.jsonl"
    retry_failed="${HYP_OUTPUT_ROOT}/${lang_lower}.retry_${RUN_ID}.failed.jsonl"
    retry_log_name="${lang_lower}.retry_${RUN_ID}"

    echo "== ${lang} failed retry start $(date -u '+%Y-%m-%dT%H:%M:%SZ') =="
    echo "retry_manifest=${failed}"
    echo "retry_output=${retry_output}"
    echo "retry_failed=${retry_failed}"
    echo "retry_existing_output_lines=$(count_lines "${retry_output}")"
    echo "retry_existing_failed_lines=$(count_lines "${retry_failed}")"
    dedupe_failed_manifest "${failed}" "${retry_manifest}"
    echo "retry_manifest=${retry_manifest}"
    echo "retry_manifest_lines=$(count_lines "${retry_manifest}")"

    (
      set -euo pipefail
      conda run -n "${ASR_ENV}" --no-capture-output python "${ASR_DIR}/verify_edit_data.py" \
        --manifest "${retry_manifest}" \
        --audio_root "${AUDIO_ROOT}" \
        --id-field id \
        --audio-field wav \
        --ref-text-field ref_text \
        --lang-field language \
        --duration-field duration \
        --ports "${PORTS}" \
        --workers-per-port "${WORKERS_PER_PORT}" \
        --max-inflight "${MAX_INFLIGHT}" \
        --timeout "${TIMEOUT}" \
        --max-retries "${MAX_RETRIES}" \
        --output "${retry_output}" \
        --failed-output "${retry_failed}" \
        "${edit_args[@]}"
    ) > >(tee -a "${FULL_RUN_DIR}/logs/${retry_log_name}.log") 2>&1 &
    child_pid=$!
    wait "${child_pid}"
    child_pid=""

    echo "== ${lang} failed retry done $(date -u '+%Y-%m-%dT%H:%M:%SZ') =="
    echo "retry_output_lines=$(count_lines "${retry_output}")"
    echo "retry_failed_lines=$(count_lines "${retry_failed}")"
    echo "${lang}=retry_done" > "${FULL_RUN_DIR}/status/${lang}.retry.done"
  else
    echo "== ${lang} failed retry skipped =="
    echo "run_failed_retry=${RUN_FAILED_RETRY}"
    echo "failed_lines=$(count_lines "${failed}")"
  fi
}

echo "full_serial_child=started"
echo "run_id=${RUN_ID}"
echo "run_dir=${FULL_RUN_DIR}"
echo "asr_env=${ASR_ENV}"
echo "ports=${PORTS}"
echo "workers_per_port=${WORKERS_PER_PORT}"
echo "max_inflight=${MAX_INFLIGHT}"
echo "run_failed_retry=${RUN_FAILED_RETRY}"
echo "lang_order=${LANG_ORDER}"
echo "hyp_output_root=${HYP_OUTPUT_ROOT}"

check_inputs

for lang in ${LANG_ORDER}; do
  run_lang "${lang}"
done

echo "full_serial=done $(date -u '+%Y-%m-%dT%H:%M:%SZ')" | tee "${FULL_RUN_DIR}/status/full_serial.done"
