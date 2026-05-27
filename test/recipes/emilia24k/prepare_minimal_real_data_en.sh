#!/usr/bin/env bash

export PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python

set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
ICEFALL_ROOT=$(cd -- "${SCRIPT_DIR}/../../.." && pwd)
RECIPE_DIR="${RECIPE_DIR:-${ICEFALL_ROOT}/egs/zipformer_24k_multilang/zipformer_24k_en/ASR}"
VALIDATION_ROOT="${VALIDATION_ROOT:-$(cd -- "${ICEFALL_ROOT}/.." && pwd)/experiments/main_flow_validation/emilia24k_en}"

ARTIFACT_ROOT="${ARTIFACT_ROOT:-${VALIDATION_ROOT}/workspace/artifacts}"
DATASET_ROOT="${DATASET_ROOT:-/inspire/dataset/emilia/fc71e07}"
LANGUAGE="${LANGUAGE:-en}"
MAX_JSONL_FILES="${MAX_JSONL_FILES:-1}"
MAX_UTTERANCES="${MAX_UTTERANCES:-64}"
RECORDING_NUM_SPLITS="${RECORDING_NUM_SPLITS:-4}"
FEATURE_NUM_SPLITS="${FEATURE_NUM_SPLITS:-4}"
FEATURE_NUM_WORKERS="${FEATURE_NUM_WORKERS:-0}"
FEATURE_BATCH_DURATION="${FEATURE_BATCH_DURATION:-80}"
STAGE="${STAGE:-0}"
STOP_STAGE="${STOP_STAGE:-10}"

mkdir -p "${VALIDATION_ROOT}" "${ARTIFACT_ROOT}"

bash "${RECIPE_DIR}/prepare.sh" \
  --language "${LANGUAGE}" \
  --dataset-root "${DATASET_ROOT}" \
  --artifact-root "${ARTIFACT_ROOT}" \
  --max-jsonl-files "${MAX_JSONL_FILES}" \
  --max-utterances "${MAX_UTTERANCES}" \
  --recording-num-splits "${RECORDING_NUM_SPLITS}" \
  --feature-num-splits "${FEATURE_NUM_SPLITS}" \
  --feature-num-workers "${FEATURE_NUM_WORKERS}" \
  --feature-batch-duration "${FEATURE_BATCH_DURATION}" \
  --feature-device cpu \
  --stage "${STAGE}" \
  --stop-stage "${STOP_STAGE}"

cat >"${VALIDATION_ROOT}/validation_summary.json" <<EOF
{
  "status": "prepared",
  "language": "${LANGUAGE}",
  "artifact_root": "${ARTIFACT_ROOT}",
  "dataset_root": "${DATASET_ROOT}"
}
EOF

echo "Prepared minimal Emilia EN validation data at ${ARTIFACT_ROOT}"
