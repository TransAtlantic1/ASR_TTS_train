#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
ICEFALL_ROOT=$(cd -- "${SCRIPT_DIR}/../../../.." && pwd)
PARSE_OPTIONS_SH="${ICEFALL_ROOT}/icefall/shared/parse_options.sh"

bench_root="/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/public/eval"
test_sets=""
test_set_preset="en-open-v1"
feature_num_workers=8
feature_batch_duration=600
feature_device=auto
skip_unavailable=false

. "${PARSE_OPTIONS_SH}" || exit 1

python3 "${SCRIPT_DIR}/../utils/prepare_bench.py" \
  --language en \
  --bench-root "${bench_root}" \
  --test-sets "${test_sets}" \
  --test-set-preset "${test_set_preset}" \
  --feature-num-workers "${feature_num_workers}" \
  --feature-batch-duration "${feature_batch_duration}" \
  --feature-device "${feature_device}" \
  $( [ "${skip_unavailable}" = true ] && printf '%s' -- "--skip-unavailable" )
