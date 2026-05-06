#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)

RAW_ROOT="${RAW_ROOT:-/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/raw_data}"
OUTPUT_ROOT="${OUTPUT_ROOT:-/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat}"
NUM_SHARDS="${NUM_SHARDS:-1}"
SHARD_INDEX="${SHARD_INDEX:-0}"
MAX_UTTERANCES_PER_LANGUAGE="${MAX_UTTERANCES_PER_LANGUAGE:--1}"
MAX_LINES_PER_LANGUAGE="${MAX_LINES_PER_LANGUAGE:--1}"
PROGRESS_PATH="${PROGRESS_PATH:-${SCRIPT_DIR}/../logs/full_prepare_en.progress.json}"
PROGRESS_INTERVAL_LINES="${PROGRESS_INTERVAL_LINES:-100000}"

python "${SCRIPT_DIR}/prepare_jellycat_en.py" \
  --raw-root "${RAW_ROOT}" \
  --output-root "${OUTPUT_ROOT}" \
  --languages en-us \
  --manifest-stem "jellycat_EN_segments" \
  --num-shards "${NUM_SHARDS}" \
  --shard-index "${SHARD_INDEX}" \
  --max-utterances-per-language "${MAX_UTTERANCES_PER_LANGUAGE}" \
  --max-lines-per-language "${MAX_LINES_PER_LANGUAGE}" \
  --progress-path "${PROGRESS_PATH}" \
  --progress-interval-lines "${PROGRESS_INTERVAL_LINES}" \
  "$@"
