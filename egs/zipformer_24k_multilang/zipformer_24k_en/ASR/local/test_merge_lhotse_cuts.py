#!/usr/bin/env python3

from pathlib import Path
from tempfile import TemporaryDirectory

from lhotse import CutSet, load_manifest
from lhotse.testing.dummies import dummy_cut

from merge_lhotse_cuts import merge_cut_manifests


def test_merge_cut_manifests(tmp_path: Path):
    cut_a = dummy_cut(0)
    cut_b = dummy_cut(1)

    input_a = tmp_path / "a.jsonl.gz"
    input_b = tmp_path / "b.jsonl.gz"
    output = tmp_path / "merged.jsonl.gz"

    CutSet.from_cuts([cut_a]).to_file(input_a)
    CutSet.from_cuts([cut_b]).to_file(input_b)

    merge_cut_manifests([input_a, input_b], output)

    merged = load_manifest(output)
    assert sorted(cut.id for cut in merged) == sorted([cut_a.id, cut_b.id])


def test_merge_cut_manifests_rejects_duplicate_ids(tmp_path: Path):
    cut = dummy_cut(0)

    input_a = tmp_path / "a.jsonl.gz"
    input_b = tmp_path / "b.jsonl.gz"
    output = tmp_path / "merged.jsonl.gz"

    CutSet.from_cuts([cut]).to_file(input_a)
    CutSet.from_cuts([cut]).to_file(input_b)

    try:
        merge_cut_manifests([input_a, input_b], output)
    except ValueError as exc:
        assert "Duplicate cut ID" in str(exc)
    else:
        raise AssertionError("Expected duplicate cut IDs to raise ValueError")


if __name__ == "__main__":
    with TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        test_merge_cut_manifests(temp_path)
        test_merge_cut_manifests_rejects_duplicate_ids(temp_path)
    print("ok")
