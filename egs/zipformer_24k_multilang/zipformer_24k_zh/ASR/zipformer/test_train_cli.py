#!/usr/bin/env python3

import os
import sys
import tempfile
from pathlib import Path

ICEFALL_ROOT = Path(__file__).resolve().parents[5]
if str(ICEFALL_ROOT) not in sys.path:
    sys.path.insert(0, str(ICEFALL_ROOT))

from asr_datamodule import EmiliaAsrDataModule
from train import get_parser, normalize_emilia_args


def parse_normalized(args):
    parser = get_parser()
    EmiliaAsrDataModule.add_arguments(parser)
    parsed = parser.parse_args(args)
    return normalize_emilia_args(parsed)


def test_dataset_jellycat_sets_manifest_prefix_and_artifact_root():
    args = parse_normalized(
        [
            "--dataset",
            "jellycat",
            "--language",
            "zh",
            "--auto-exp-subdir",
            "false",
        ]
    )

    assert args.dataset == "jellycat"
    assert args.manifest_prefix == "jellycat_zh"
    assert args.artifact_root.endswith(
        "/public/jellycat/full/icefall_jellycat_zh_24k"
    )


def test_zh_accepts_external_dev_cuts_path():
    dev_cuts_path = Path("/tmp/example_dev_cuts.jsonl.gz")
    args = parse_normalized(
        [
            "--dataset",
            "jellycat",
            "--language",
            "zh",
            "--auto-exp-subdir",
            "false",
            "--dev-cuts-path",
            str(dev_cuts_path),
        ]
    )

    assert args.dev_cuts_path == dev_cuts_path


def test_jellycat_prefers_data_fbank_manifest_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        artifact_root = Path(tmpdir)
        (artifact_root / "data" / "fbank" / "zh").mkdir(parents=True)
        (artifact_root / "data_clean_20260510T153150Z" / "fbank" / "zh").mkdir(
            parents=True
        )

        args = parse_normalized(
            [
                "--dataset",
                "jellycat",
                "--language",
                "zh",
                "--auto-exp-subdir",
                "false",
                "--artifact-root",
                str(artifact_root),
            ]
        )

    assert args.manifest_dir == artifact_root / "data" / "fbank"


def test_jellycat_default_ignores_emilia_artifact_env():
    old_value = os.environ.get("EMILIA_ARTIFACT_ROOT")
    os.environ["EMILIA_ARTIFACT_ROOT"] = "/tmp/wrong_emilia_root"
    try:
        args = parse_normalized(
            [
                "--dataset",
                "jellycat",
                "--language",
                "zh",
                "--auto-exp-subdir",
                "false",
            ]
        )
    finally:
        if old_value is None:
            os.environ.pop("EMILIA_ARTIFACT_ROOT", None)
        else:
            os.environ["EMILIA_ARTIFACT_ROOT"] = old_value

    assert args.artifact_root.endswith(
        "/public/jellycat/full/icefall_jellycat_zh_24k"
    )


if __name__ == "__main__":
    test_dataset_jellycat_sets_manifest_prefix_and_artifact_root()
    test_zh_accepts_external_dev_cuts_path()
    test_jellycat_prefers_data_fbank_manifest_dir()
    test_jellycat_default_ignores_emilia_artifact_env()
    print("ok")
