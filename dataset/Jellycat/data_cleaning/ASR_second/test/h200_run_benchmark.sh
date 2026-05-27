#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ASR_DIR=$(cd "${SCRIPT_DIR}/.." && pwd)

: "${RUN_DIR:=${SCRIPT_DIR}/runs/latest}"
if [[ -f "${RUN_DIR}/run_env.sh" ]]; then
  # shellcheck source=/dev/null
  source "${RUN_DIR}/run_env.sh"
fi

: "${ASR_ENV:=meanaudio2}"
: "${AUDIO_ROOT:=/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat}"
: "${ZH_MANIFEST:=${AUDIO_ROOT}/manifests/ZH/jellycat_ZH_segments.jsonl.gz}"
: "${EN_MANIFEST:=${AUDIO_ROOT}/manifests/EN/jellycat_EN_segments.jsonl.gz}"
: "${PORTS:=8000,8001,8002,8003,8004,8005,8006,8007}"
: "${LIMIT:=100}"
: "${LANGS:=ZH EN}"
: "${WORKERS_PER_PORT:=1}"
: "${MAX_INFLIGHT:=32}"
: "${TIMEOUT:=600}"
: "${MAX_RETRIES:=2}"
: "${INCLUDE_EDITS:=1}"
: "${LABEL:=limit${LIMIT}_wpp${WORKERS_PER_PORT}}"

BENCH_DIR="${RUN_DIR}/benchmarks"
mkdir -p "${BENCH_DIR}" "${RUN_DIR}/status"
exec > >(tee -a "${RUN_DIR}/benchmark_${LABEL}.log") 2>&1

manifest_for_lang() {
  case "$1" in
    ZH|zh) echo "${ZH_MANIFEST}" ;;
    EN|en) echo "${EN_MANIFEST}" ;;
    *) echo "unsupported language: $1" >&2; return 2 ;;
  esac
}

lower_lang() {
  echo "$1" | tr '[:upper:]' '[:lower:]'
}

EDIT_ARGS=()
if [[ "${INCLUDE_EDITS}" == "0" ]]; then
  EDIT_ARGS+=(--no-edits)
fi

echo "run_dir=${RUN_DIR}"
echo "label=${LABEL}"
echo "ports=${PORTS}"
echo "limit=${LIMIT}"
echo "workers_per_port=${WORKERS_PER_PORT}"
echo "max_inflight=${MAX_INFLIGHT}"

for lang in ${LANGS}; do
  manifest=$(manifest_for_lang "${lang}")
  lang_lower=$(lower_lang "${lang}")
  out="${BENCH_DIR}/${LABEL}_${lang_lower}.jsonl"
  failed="${BENCH_DIR}/${LABEL}_${lang_lower}.failed.jsonl"
  timing="${BENCH_DIR}/${LABEL}_${lang_lower}.time.json"

  if [[ -e "${out}" || -e "${failed}" || -e "${timing}" ]]; then
    echo "benchmark outputs already exist for ${LABEL}_${lang_lower}; choose a new LABEL" >&2
    exit 2
  fi

  echo "== Benchmark ${lang} =="
  start_ns=$(date +%s%N)
  conda run -n "${ASR_ENV}" python "${ASR_DIR}/verify_edit_data.py" \
    --manifest "${manifest}" \
    --limit "${LIMIT}" \
    --audio_root "${AUDIO_ROOT}" \
    --ports "${PORTS}" \
    --workers-per-port "${WORKERS_PER_PORT}" \
    --timeout "${TIMEOUT}" \
    --max-retries "${MAX_RETRIES}" \
    --max-inflight "${MAX_INFLIGHT}" \
    --output "${out}" \
    --failed-output "${failed}" \
    "${EDIT_ARGS[@]}"
  end_ns=$(date +%s%N)

  python3 - "${timing}" "${lang}" "${LIMIT}" "${WORKERS_PER_PORT}" "${MAX_INFLIGHT}" \
    "${start_ns}" "${end_ns}" "${out}" "${failed}" "${PORTS}" <<'PY'
import json
import sys

timing, lang, limit, workers, max_inflight, start_ns, end_ns, out, failed, ports = sys.argv[1:]
start_ns = int(start_ns)
end_ns = int(end_ns)
payload = {
    "language": lang,
    "limit": int(limit),
    "workers_per_port": int(workers),
    "max_inflight": int(max_inflight),
    "start_ns": start_ns,
    "end_ns": end_ns,
    "wall_sec": (end_ns - start_ns) / 1_000_000_000,
    "output": out,
    "failed_output": failed,
    "ports": ports,
}
with open(timing, "w", encoding="utf-8") as f:
    json.dump(payload, f, indent=2, ensure_ascii=False)
    f.write("\n")
PY
done

python3 "${SCRIPT_DIR}/summarize_benchmark.py" --run-dir "${RUN_DIR}"
echo "benchmark=${LABEL}=done" | tee "${RUN_DIR}/status/benchmark_${LABEL}.done"
