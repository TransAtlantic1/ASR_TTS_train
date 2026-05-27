#!/usr/bin/env python3

import os
import sys
import tempfile
from pathlib import Path

ICEFALL_ROOT = Path(__file__).resolve().parents[5]
if str(ICEFALL_ROOT) not in sys.path:
    sys.path.insert(0, str(ICEFALL_ROOT))

from train import get_parser
from train import normalize_emilia_args
from asr_datamodule import EmiliaAsrDataModule


def test_valid_interval_default():
    args = get_parser().parse_args([])
    assert args.valid_interval == 20000


def test_valid_interval_override():
    args = get_parser().parse_args(["--valid-interval", "1000"])
    assert args.valid_interval == 1000


def test_dataset_jellycat_sets_manifest_prefix_and_artifact_root():
    parser = get_parser()
    EmiliaAsrDataModule.add_arguments(parser)
    args = parser.parse_args(["--dataset", "jellycat", "--language", "en"])
    args = normalize_emilia_args(args)

    assert args.dataset == "jellycat"
    assert args.manifest_prefix == "jellycat_en"
    assert args.artifact_root.endswith(
        "/public/jellycat/full/icefall_jellycat_en_24k"
    )


def test_manifest_prefix_can_be_overridden():
    parser = get_parser()
    EmiliaAsrDataModule.add_arguments(parser)
    args = parser.parse_args(
        [
            "--dataset",
            "jellycat",
            "--language",
            "en",
            "--manifest-prefix",
            "custom_en",
        ]
    )
    args = normalize_emilia_args(args)

    assert args.manifest_prefix == "custom_en"


def test_jellycat_discovers_data_clean_manifest_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        artifact_root = Path(tmpdir)
        manifest_dir = artifact_root / "data_clean_20260510T153150Z" / "fbank" / "en"
        manifest_dir.mkdir(parents=True)

        parser = get_parser()
        EmiliaAsrDataModule.add_arguments(parser)
        args = parser.parse_args(
            [
                "--dataset",
                "jellycat",
                "--language",
                "en",
                "--artifact-root",
                str(artifact_root),
            ]
        )
        args = normalize_emilia_args(args)

    assert args.manifest_dir == manifest_dir


def test_jellycat_default_ignores_emilia_artifact_env():
    old_value = os.environ.get("EMILIA_ARTIFACT_ROOT")
    os.environ["EMILIA_ARTIFACT_ROOT"] = "/tmp/wrong_emilia_root"
    try:
        parser = get_parser()
        EmiliaAsrDataModule.add_arguments(parser)
        args = parser.parse_args(["--dataset", "jellycat", "--language", "en"])
        args = normalize_emilia_args(args)
    finally:
        if old_value is None:
            os.environ.pop("EMILIA_ARTIFACT_ROOT", None)
        else:
            os.environ["EMILIA_ARTIFACT_ROOT"] = old_value

    assert args.artifact_root.endswith(
        "/public/jellycat/full/icefall_jellycat_en_24k"
    )


if __name__ == "__main__":
    test_valid_interval_default()
    test_valid_interval_override()
    test_dataset_jellycat_sets_manifest_prefix_and_artifact_root()
    test_manifest_prefix_can_be_overridden()
    test_jellycat_discovers_data_clean_manifest_dir()
    test_jellycat_default_ignores_emilia_artifact_env()
    print("ok")
