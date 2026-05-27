#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
JELLYCAT_ROOT=$(cd -- "${SCRIPT_DIR}/../.." && pwd)

RAW_ROOT="${RAW_ROOT:-/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/raw_data}"
OUTPUT_ROOT="${OUTPUT_ROOT:-/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat}"
NUM_SHARDS="${NUM_SHARDS:-1}"
SHARD_INDEX="${SHARD_INDEX:-0}"
MAX_UTTERANCES_PER_LANGUAGE="${MAX_UTTERANCES_PER_LANGUAGE:--1}"
MAX_LINES_PER_LANGUAGE="${MAX_LINES_PER_LANGUAGE:--1}"
PROGRESS_PATH="${PROGRESS_PATH:-${JELLYCAT_ROOT}/logs/full_prepare.progress.json}"
PROGRESS_INTERVAL_LINES="${PROGRESS_INTERVAL_LINES:-100000}"

python "${SCRIPT_DIR}/prepare_jellycat_zh.py" \
  --raw-root "${RAW_ROOT}" \
  --output-root "${OUTPUT_ROOT}" \
  --languages zh zh-cn \
  --manifest-stem "jellycat_ZH_segments" \
  --num-shards "${NUM_SHARDS}" \
  --shard-index "${SHARD_INDEX}" \
  --max-utterances-per-language "${MAX_UTTERANCES_PER_LANGUAGE}" \
  --max-lines-per-language "${MAX_LINES_PER_LANGUAGE}" \
  --progress-path "${PROGRESS_PATH}" \
  --progress-interval-lines "${PROGRESS_INTERVAL_LINES}" \
  "$@"
