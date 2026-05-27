#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
JELLYCAT_ROOT=$(cd -- "${SCRIPT_DIR}/../.." && pwd)
POLICY_DIR="${JELLYCAT_ROOT}/data_cleaning/manifest_policy_filter"

OUTPUT_ROOT="${OUTPUT_ROOT:-/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat}"
LOG_DIR="${LOG_DIR:-${JELLYCAT_ROOT}/logs}"
REPORT_DIR="${REPORT_DIR:-${JELLYCAT_ROOT}/data_cleaning/raw_to_utterance/reports}"
README_OUTPUT="${README_OUTPUT:-${REPORT_DIR}/Jellycat_EN_full_dataset_readme.md}"
MANIFEST_STEM="${MANIFEST_STEM:-jellycat_EN_segments}"
NUM_SHARDS="${NUM_SHARDS:-16}"
SLEEP_SECONDS="${SLEEP_SECONDS:-60}"

MANIFEST_DIR="${OUTPUT_ROOT}/manifests/EN"
SUMMARY_PATH="${MANIFEST_DIR}/${MANIFEST_STEM}.summary.json"
SEGMENT_PATH="${MANIFEST_DIR}/${MANIFEST_STEM}.jsonl.gz"
PODCAST_SUMMARY_PATH="${MANIFEST_DIR}/${MANIFEST_STEM}.podcast_manifests.summary.json"

mkdir -p "${LOG_DIR}"
echo "$$" > "${LOG_DIR}/finalize_jellycat_en_outputs.pid"
echo "waiting" > "${LOG_DIR}/finalize_jellycat_en_outputs.status"

while true; do
  if [ -f "${LOG_DIR}/full_prepare_en_sharded.status" ]; then
    status=$(cat "${LOG_DIR}/full_prepare_en_sharded.status")
    if [ "${status}" = "failed" ]; then
      echo "failed" > "${LOG_DIR}/finalize_jellycat_en_outputs.status"
      echo "full_prepare_en_sharded.status=failed" >&2
      exit 1
    fi
  fi

  done_count=0
  for shard_index in $(seq 0 "$((NUM_SHARDS - 1))"); do
    shard_label=$(printf 'shard%05d-of-%05d' "${shard_index}" "${NUM_SHARDS}")
    exit_file="${LOG_DIR}/full_prepare_en.${shard_label}.exit_status"
    if [ -f "${exit_file}" ] && [ "$(cat "${exit_file}")" = "0" ]; then
      done_count=$((done_count + 1))
    fi
  done

  if [ "${done_count}" -eq "${NUM_SHARDS}" ]; then
    break
  fi

  echo "waiting ${done_count}/${NUM_SHARDS} shards"
  sleep "${SLEEP_SECONDS}"
done

echo "postprocessing" > "${LOG_DIR}/finalize_jellycat_en_outputs.status"

if [ ! -f "${SEGMENT_PATH}" ]; then
  python "${SCRIPT_DIR}/merge_jellycat_sharded_manifests.py" \
    --manifest-dir "${MANIFEST_DIR}" \
    --stem "jellycat_EN" \
    --num-shards "${NUM_SHARDS}"
fi

python "${SCRIPT_DIR}/write_jellycat_podcast_manifests.py" \
  --segment-manifest "${SEGMENT_PATH}" \
  --output-root "${OUTPUT_ROOT}" \
  --language EN \
  --summary "${SUMMARY_PATH}" \
  --summary-output "${PODCAST_SUMMARY_PATH}" \
  --progress-path "${LOG_DIR}/full_prepare_en_podcast_manifests.progress.json" \
  --overwrite

python "${POLICY_DIR}/write_jellycat_full_readme.py" \
  --summary "${SUMMARY_PATH}" \
  --output "${README_OUTPUT}"

echo "done" > "${LOG_DIR}/finalize_jellycat_en_outputs.status"
