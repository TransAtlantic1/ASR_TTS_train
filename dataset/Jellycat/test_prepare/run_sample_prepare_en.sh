#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd -- "${SCRIPT_DIR}/../../.." && pwd)

RAW_ROOT="${RAW_ROOT:-/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/raw_data}"
SAMPLE_ROOT="${SAMPLE_ROOT:-${REPO_ROOT}/dataset/Jellycat/sample_en}"
MAX_UTTERANCES_PER_LANGUAGE="${MAX_UTTERANCES_PER_LANGUAGE:-8}"
MAX_LINES_PER_LANGUAGE="${MAX_LINES_PER_LANGUAGE:-2000}"

rm -rf "${SAMPLE_ROOT}"

python "${REPO_ROOT}/dataset/Jellycat/prepare_data/prepare_jellycat_en.py" \
  --raw-root "${RAW_ROOT}" \
  --output-root "${SAMPLE_ROOT}" \
  --languages en-us \
  --manifest-stem "jellycat_EN_segments.sample" \
  --max-utterances-per-language "${MAX_UTTERANCES_PER_LANGUAGE}" \
  --max-lines-per-language "${MAX_LINES_PER_LANGUAGE}" \
  --overwrite

python "${SCRIPT_DIR}/validate_jellycat_en_sample.py" \
  --sample-root "${SAMPLE_ROOT}"
