#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
JELLYCAT_ROOT=$(cd -- "${SCRIPT_DIR}/../../.." && pwd)

RAW_ROOT="${RAW_ROOT:-/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/raw_data}"
SAMPLE_ROOT="${SAMPLE_ROOT:-${JELLYCAT_ROOT}/sample}"
MAX_UTTERANCES_PER_LANGUAGE="${MAX_UTTERANCES_PER_LANGUAGE:-8}"
MAX_LINES_PER_LANGUAGE="${MAX_LINES_PER_LANGUAGE:-2000}"

rm -rf "${SAMPLE_ROOT}"

python "${JELLYCAT_ROOT}/data_cleaning/raw_to_utterance/prepare_jellycat_zh.py" \
  --raw-root "${RAW_ROOT}" \
  --output-root "${SAMPLE_ROOT}" \
  --languages zh zh-cn \
  --manifest-stem "jellycat_ZH_segments.sample" \
  --max-utterances-per-language "${MAX_UTTERANCES_PER_LANGUAGE}" \
  --max-lines-per-language "${MAX_LINES_PER_LANGUAGE}" \
  --overwrite

python "${SCRIPT_DIR}/validate_jellycat_sample.py" \
  --sample-root "${SAMPLE_ROOT}"
