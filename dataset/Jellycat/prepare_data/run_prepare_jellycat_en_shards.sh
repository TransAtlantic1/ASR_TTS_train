#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd -- "${SCRIPT_DIR}/../../.." && pwd)

RAW_ROOT="${RAW_ROOT:-/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/raw_data}"
OUTPUT_ROOT="${OUTPUT_ROOT:-/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat}"
LOG_DIR="${LOG_DIR:-${REPO_ROOT}/dataset/Jellycat/logs}"
README_OUTPUT="${README_OUTPUT:-${REPO_ROOT}/dataset/Jellycat/readme/Jellycat_EN_full_dataset_readme.md}"
NUM_SHARDS="${NUM_SHARDS:-16}"
MAX_PARALLEL="${MAX_PARALLEL:-16}"
PROGRESS_INTERVAL_LINES="${PROGRESS_INTERVAL_LINES:-100000}"
MANIFEST_STEM="${MANIFEST_STEM:-jellycat_EN_segments}"

mkdir -p "${LOG_DIR}"
echo "$$" > "${LOG_DIR}/full_prepare_en_sharded.launcher.pid"
echo "running" > "${LOG_DIR}/full_prepare_en_sharded.status"

start_shard() {
  local shard_index=$1
  local shard_label
  shard_label=$(printf 'shard%05d-of-%05d' "${shard_index}" "${NUM_SHARDS}")
  (
    set -uo pipefail
    echo "running" > "${LOG_DIR}/full_prepare_en.${shard_label}.status"
    date -u
    python "${SCRIPT_DIR}/prepare_jellycat_en.py" \
      --raw-root "${RAW_ROOT}" \
      --output-root "${OUTPUT_ROOT}" \
      --languages en-us \
      --manifest-stem "${MANIFEST_STEM}" \
      --num-shards "${NUM_SHARDS}" \
      --shard-index "${shard_index}" \
      --progress-path "${LOG_DIR}/full_prepare_en.${shard_label}.progress.json" \
      --progress-interval-lines "${PROGRESS_INTERVAL_LINES}"
    status=$?
    date -u
    echo "${status}" > "${LOG_DIR}/full_prepare_en.${shard_label}.exit_status"
    if [ "${status}" -eq 0 ]; then
      echo "done" > "${LOG_DIR}/full_prepare_en.${shard_label}.status"
    else
      echo "failed" > "${LOG_DIR}/full_prepare_en.${shard_label}.status"
    fi
    exit "${status}"
  ) > "${LOG_DIR}/full_prepare_en.${shard_label}.log" 2>&1 &
  echo "$!" > "${LOG_DIR}/full_prepare_en.${shard_label}.pid"
  pids+=("$!")
}

pids=()
for shard_index in $(seq 0 "$((NUM_SHARDS - 1))"); do
  while [ "$(jobs -rp | wc -l)" -ge "${MAX_PARALLEL}" ]; do
    sleep 10
  done
  start_shard "${shard_index}"
done

failed=0
for pid in "${pids[@]}"; do
  if ! wait "${pid}"; then
    failed=1
  fi
done

if [ "${failed}" -eq 0 ]; then
  python "${SCRIPT_DIR}/merge_jellycat_sharded_manifests.py" \
    --manifest-dir "${OUTPUT_ROOT}/manifests/EN" \
    --stem "jellycat_EN" \
    --num-shards "${NUM_SHARDS}"
  python "${SCRIPT_DIR}/write_jellycat_podcast_manifests.py" \
    --segment-manifest "${OUTPUT_ROOT}/manifests/EN/${MANIFEST_STEM}.jsonl.gz" \
    --output-root "${OUTPUT_ROOT}" \
    --language EN \
    --summary "${OUTPUT_ROOT}/manifests/EN/${MANIFEST_STEM}.summary.json" \
    --summary-output "${OUTPUT_ROOT}/manifests/EN/${MANIFEST_STEM}.podcast_manifests.summary.json" \
    --progress-path "${LOG_DIR}/full_prepare_en_podcast_manifests.progress.json" \
    --overwrite
  python "${SCRIPT_DIR}/write_jellycat_full_readme.py" \
    --summary "${OUTPUT_ROOT}/manifests/EN/${MANIFEST_STEM}.summary.json" \
    --output "${README_OUTPUT}"
  echo "done" > "${LOG_DIR}/full_prepare_en_sharded.status"
else
  echo "failed" > "${LOG_DIR}/full_prepare_en_sharded.status"
fi

exit "${failed}"
