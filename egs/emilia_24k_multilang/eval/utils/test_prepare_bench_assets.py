#!/usr/bin/env python3

from __future__ import annotations

import gzip
import json
import wave
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

import numpy as np
from lhotse import CutSet, Recording, RecordingSet
from lhotse.features import Features
from lhotse.features.io import LilcomChunkyWriter
from lhotse.supervision import SupervisionSegment
from lhotse.testing.dummies import dummy_cut
from lhotse.utils import fastcopy

from prepare_bench import (
    _build_thchs30_subset_manifests,
    _align_trimmed_single_supervision_durations,
    _build_voxpopuli_accented_test_manifests,
    _load_thchs30_transcript,
    _load_thchs30_noise_transcript,
    _load_transcript,
    _thchs_noise_label,
    _voxpopuli_recording_id,
    assert_prepared_cutset_invariants,
)
import validate_bench_assets as validate_bench_assets_module
from compute_eval_features import align_cutset_to_feature_durations
from validate_bench_assets import (
    DatasetValidationResult,
    validate_dataset_assets,
    write_available_dataset_summary,
)


def _write_lca_features(
    dataset_root: Path,
    dataset_id: str,
    *,
    actual_num_frames: int,
    manifest_num_frames: int | None = None,
    cut_num_frames: int | None = None,
    storage_dataset_root: Path | None = None,
    cut_id: str = "cut-0",
):
    storage_root = storage_dataset_root or dataset_root
    storage_path = storage_root / "fbank" / f"{dataset_id}_feats.lca"
    storage_path.parent.mkdir(parents=True, exist_ok=True)

    with LilcomChunkyWriter(storage_path) as writer:
        storage_key = writer.write(cut_id, np.ones((actual_num_frames, 23), dtype=np.float32))

    frame_shift = 0.01
    feature_duration = (manifest_num_frames or actual_num_frames) * frame_shift
    cut_duration = (cut_num_frames or manifest_num_frames or actual_num_frames) * frame_shift
    features = Features(
        type="fbank",
        num_frames=manifest_num_frames or actual_num_frames,
        num_features=23,
        frame_shift=frame_shift,
        sampling_rate=16000,
        start=0.0,
        duration=feature_duration,
        storage_type="lilcom_chunky",
        storage_path=str(storage_path),
        storage_key=storage_key,
        recording_id="dummy-recording-0000",
        channels=0,
    )
    cut = dummy_cut(0, duration=cut_duration, features=features)
    supervision = SupervisionSegment(
        id=f"sup-{cut_id}",
        recording_id="dummy-recording-0000",
        start=0.0,
        duration=cut_duration,
        text=f"text-{cut_id}",
    )
    cut = fastcopy(cut, id=cut_id, supervisions=[supervision])
    return cut, storage_path


def _write_sharded_lca_features(
    dataset_root: Path,
    dataset_id: str,
    *,
    actual_num_frames: int,
    manifest_num_frames: int | None = None,
    cut_num_frames: int | None = None,
    cut_id: str = "cut-0",
    shard_name: str = "feats-0.lca",
):
    storage_path = dataset_root / "fbank" / f"{dataset_id}_feats" / shard_name
    storage_path.parent.mkdir(parents=True, exist_ok=True)

    with LilcomChunkyWriter(storage_path) as writer:
        storage_key = writer.write(cut_id, np.ones((actual_num_frames, 23), dtype=np.float32))

    frame_shift = 0.01
    feature_duration = (manifest_num_frames or actual_num_frames) * frame_shift
    cut_duration = (cut_num_frames or manifest_num_frames or actual_num_frames) * frame_shift
    features = Features(
        type="fbank",
        num_frames=manifest_num_frames or actual_num_frames,
        num_features=23,
        frame_shift=frame_shift,
        sampling_rate=16000,
        start=0.0,
        duration=feature_duration,
        storage_type="lilcom_chunky",
        storage_path=str(storage_path),
        storage_key=storage_key,
        recording_id="dummy-recording-0000",
        channels=0,
    )
    cut = dummy_cut(0, duration=cut_duration, features=features)
    supervision = SupervisionSegment(
        id=f"sup-{cut_id}",
        recording_id="dummy-recording-0000",
        start=0.0,
        duration=cut_duration,
        text=f"text-{cut_id}",
    )
    cut = fastcopy(cut, id=cut_id, supervisions=[supervision])
    return cut, storage_path


def _write_dataset(
    root: Path,
    dataset_id: str,
    cuts,
    *,
    raw_cuts=None,
):
    dataset_root = root / dataset_id
    raw_dir = dataset_root / "raw_cuts"
    fbank_dir = dataset_root / "fbank"
    raw_dir.mkdir(parents=True, exist_ok=True)
    fbank_dir.mkdir(parents=True, exist_ok=True)

    (raw_cuts or cuts).to_file(raw_dir / f"{dataset_id}_cuts_raw.jsonl.gz")
    cuts.to_file(fbank_dir / f"{dataset_id}_cuts.jsonl.gz")
    return dataset_root


def _link_prepared_lca(dataset_root: Path, dataset_id: str, target_path: Path) -> Path:
    prepared_lca = dataset_root / "fbank" / f"{dataset_id}_feats.lca"
    prepared_lca.symlink_to(target_path)
    return prepared_lca


def _write_test_wav(path: Path, *, sample_rate: int = 16000, num_samples: int = 1600):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(b"\x00\x00" * num_samples)


def _write_voxpopuli_accented_tsv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "id_|paragraph_id|session_id|speaker_id|original_text|normed_text|decoded|"
        "start_time|end_time|cer|wer|vad|split|gender|accent|is_gold_transcript"
    )
    with gzip.open(path, "wt", encoding="utf-8") as f:
        f.write(header + "\n")
        for row in rows:
            f.write("|".join(row[column] for column in header.split("|")) + "\n")


@dataclass
class _FakeFeatures:
    storage_path: str
    num_frames: int


@dataclass
class _FakeCut:
    id: str
    duration: float
    num_frames: int | None
    features: _FakeFeatures
    loaded_num_frames: int

    def load_features(self):
        return np.ones((self.loaded_num_frames, 23), dtype=np.float32)


def test_thchs_noise_label_uses_noise_root_relative_path(tmp_path: Path):
    noise_root = tmp_path / "test-noise"
    wav_path = (
        tmp_path
        / "thchs30_noise_white"
        / "download"
        / "test-noise"
        / "0db"
        / "cafe"
        / "D11_750.wav"
    )
    noise_root = wav_path.parents[2]
    assert _thchs_noise_label(wav_path, noise_root) == "cafe"


def test_load_thchs30_noise_transcript_resolves_pointer_file(tmp_path: Path):
    data_trn = tmp_path / "data" / "D11_750.wav.trn"
    data_trn.parent.mkdir(parents=True, exist_ok=True)
    data_trn.write_text("东北军 的 一些 爱国 将士\n", encoding="utf-8")

    pointer_trn = tmp_path / "test" / "D11_750.wav.trn"
    pointer_trn.parent.mkdir(parents=True, exist_ok=True)
    pointer_trn.write_text("../data/D11_750.wav.trn\n", encoding="utf-8")

    assert _load_thchs30_noise_transcript(pointer_trn) == "东北军 的 一些 爱国 将士"


def test_load_thchs30_transcript_resolves_pointer_file(tmp_path: Path):
    data_trn = tmp_path / "data" / "D11_750.wav.trn"
    data_trn.parent.mkdir(parents=True, exist_ok=True)
    data_trn.write_text("东北军 的 一些 爱国 将士\n", encoding="utf-8")

    pointer_trn = tmp_path / "test" / "D11_750.wav.trn"
    pointer_trn.parent.mkdir(parents=True, exist_ok=True)
    pointer_trn.write_text("../data/D11_750.wav.trn\n", encoding="utf-8")

    assert _load_thchs30_transcript(pointer_trn) == "东北军 的 一些 爱国 将士"


def test_build_thchs30_subset_manifests_resolves_pointer_transcript_for_thchs30_test(
    tmp_path: Path,
):
    corpus_root = tmp_path / "data_thchs30"
    _write_test_wav(corpus_root / "test" / "D11_750.wav")
    (corpus_root / "data").mkdir(parents=True, exist_ok=True)
    (corpus_root / "data" / "D11_750.wav.trn").write_text(
        "东北军 的 一些 爱国 将士\n",
        encoding="utf-8",
    )
    (corpus_root / "test" / "D11_750.wav.trn").write_text(
        "../data/D11_750.wav.trn\n",
        encoding="utf-8",
    )

    _, supervisions = _build_thchs30_subset_manifests(corpus_root, "test")
    supervision = next(iter(supervisions))

    assert supervision.text == "东北军 的 一些 爱国 将士"
    assert supervision.custom["raw_text"] == "东北军 的 一些 爱国 将士"


def test_load_transcript_keeps_existing_single_line_behavior(tmp_path: Path):
    transcript_path = tmp_path / "D11_750.wav.trn"
    transcript_path.write_text("../data/D11_750.wav.trn\n", encoding="utf-8")

    assert _load_transcript(transcript_path) == "../data/D11_750.wav.trn"


def test_voxpopuli_recording_id_strips_language_suffix():
    assert _voxpopuli_recording_id(Path("20090204-0900-PLENARY-3_en.ogg")) == (
        "20090204-0900-PLENARY-3"
    )
    assert _voxpopuli_recording_id(Path("20090204-0900-PLENARY-3_original.ogg")) == (
        "20090204-0900-PLENARY-3"
    )


def test_build_voxpopuli_accented_test_manifests_uses_dedicated_annotations(
    tmp_path: Path,
):
    session_a = tmp_path / "session-a.wav"
    session_b = tmp_path / "session-b.wav"
    _write_test_wav(session_a)
    _write_test_wav(session_b)

    recordings = RecordingSet.from_recordings(
        [
            Recording.from_file(str(session_a), recording_id="session-a"),
            Recording.from_file(str(session_b), recording_id="session-b"),
        ]
    )
    annotations_path = tmp_path / "asr_en_accented.tsv.gz"
    _write_voxpopuli_accented_tsv(
        annotations_path,
        [
            {
                "id_": "row-1",
                "paragraph_id": "para-1",
                "session_id": "session-a",
                "speaker_id": "speaker-a",
                "original_text": "Original one.",
                "normed_text": "original one",
                "decoded": "decoded one",
                "start_time": "0.0",
                "end_time": "0.1",
                "cer": "0.0",
                "wer": "0.0",
                "vad": "[[0.0, 0.1]]",
                "split": "test",
                "gender": "female",
                "accent": "en_cs",
                "is_gold_transcript": "True",
            },
            {
                "id_": "row-2",
                "paragraph_id": "para-2",
                "session_id": "session-b",
                "speaker_id": "speaker-b",
                "original_text": "Original two.",
                "normed_text": "original two",
                "decoded": "decoded two",
                "start_time": "0.0",
                "end_time": "0.1",
                "cer": "0.0",
                "wer": "0.0",
                "vad": "[[0.0, 0.1]]",
                "split": "dev",
                "gender": "male",
                "accent": "en_de",
                "is_gold_transcript": "False",
            },
        ],
    )

    accented_recordings, accented_supervisions = _build_voxpopuli_accented_test_manifests(
        recordings, annotations_path
    )

    assert {recording.id for recording in accented_recordings} == {"session-a"}
    supervision = next(iter(accented_supervisions))
    assert supervision.recording_id == "session-a"
    assert supervision.custom["accent"] == "en_cs"
    assert supervision.custom["is_gold_transcript"] is True
    assert supervision.custom["orig_text"] == "Original one."


def test_align_trimmed_single_supervision_durations_repairs_tiny_float_drift():
    cut, _ = _write_lca_features(
        Path("/tmp") / "unused",
        "thchs30_test",
        actual_num_frames=100,
    )
    repaired = fastcopy(
        cut,
        duration=2.2399375,
        supervisions=[fastcopy(cut.supervisions[0], duration=2.23993)],
    )

    repaired_cutset = _align_trimmed_single_supervision_durations(
        CutSet.from_cuts([repaired])
    )
    result = next(iter(repaired_cutset))

    assert result.duration == 2.2399375
    assert result.supervisions[0].duration == 2.2399375


def test_align_trimmed_single_supervision_durations_keeps_non_trimmed_cuts_strict():
    cut, _ = _write_lca_features(
        Path("/tmp") / "unused-non-trimmed",
        "thchs30_test",
        actual_num_frames=100,
    )
    not_trimmed = fastcopy(
        cut,
        duration=2.2399375,
        supervisions=[
            fastcopy(cut.supervisions[0], start=0.1, duration=2.23993)
        ],
    )

    repaired_cutset = _align_trimmed_single_supervision_durations(
        CutSet.from_cuts([not_trimmed])
    )
    result = next(iter(repaired_cutset))

    assert result.duration == 2.2399375
    assert result.supervisions[0].start == 0.1
    assert result.supervisions[0].duration == 2.23993


def test_align_trimmed_single_supervision_durations_keeps_large_drift_strict():
    cut, _ = _write_lca_features(
        Path("/tmp") / "unused-large-drift",
        "thchs30_test",
        actual_num_frames=100,
    )
    large_drift = fastcopy(
        cut,
        duration=2.2399375,
        supervisions=[fastcopy(cut.supervisions[0], duration=2.238)],
    )

    repaired_cutset = _align_trimmed_single_supervision_durations(
        CutSet.from_cuts([large_drift])
    )
    try:
        assert_prepared_cutset_invariants(repaired_cutset, "thchs30_test")
    except ValueError as ex:
        assert "durations to match" in str(ex)
    else:
        raise AssertionError("Expected invariant failure for large duration drift")


def test_align_cutset_to_feature_durations_repairs_tiny_drift():
    cut, storage_path = _write_lca_features(
        Path("/tmp") / "unused-feature-duration",
        "thchs30_test",
        actual_num_frames=1834,
        manifest_num_frames=1834,
        cut_num_frames=1834,
    )
    repaired = fastcopy(
        cut,
        duration=cut.features.duration - 7.5e-05,
        supervisions=[
            fastcopy(cut.supervisions[0], duration=cut.features.duration - 7.5e-05)
        ],
    )

    aligned = align_cutset_to_feature_durations(
        CutSet.from_cuts([repaired]), storage_path
    )
    result = next(iter(aligned))

    assert result.duration == result.features.duration
    assert result.supervisions[0].duration == result.features.duration


def test_align_cutset_to_feature_durations_keeps_large_drift_strict():
    cut, storage_path = _write_lca_features(
        Path("/tmp") / "unused-feature-duration-large",
        "thchs30_test",
        actual_num_frames=1834,
        manifest_num_frames=1834,
        cut_num_frames=1834,
    )
    large_drift = fastcopy(
        cut,
        duration=cut.features.duration - 0.02,
        supervisions=[fastcopy(cut.supervisions[0], duration=cut.features.duration - 0.02)],
    )

    aligned = align_cutset_to_feature_durations(
        CutSet.from_cuts([large_drift]), storage_path
    )
    result = next(iter(aligned))

    assert result.duration == cut.features.duration - 0.02
    assert result.supervisions[0].duration == cut.features.duration - 0.02


def test_validate_dataset_assets_accepts_valid_local_storage(tmp_path: Path):
    dataset_id = "thchs30_test"
    cut, _ = _write_lca_features(
        tmp_path / dataset_id,
        dataset_id,
        actual_num_frames=100,
    )
    cuts = CutSet.from_cuts([cut])
    _write_dataset(tmp_path, dataset_id, cuts)

    result = validate_dataset_assets(tmp_path, dataset_id, check_run_eval_zh=False)
    assert result.ok
    assert result.issue_count == 0


def test_validate_dataset_assets_accepts_valid_local_sharded_storage(tmp_path: Path):
    dataset_id = "LIBRISPEECH_TEST_CLEAN"
    cut, _ = _write_sharded_lca_features(
        tmp_path / dataset_id,
        dataset_id,
        actual_num_frames=100,
    )
    cuts = CutSet.from_cuts([cut])
    _write_dataset(tmp_path, dataset_id, cuts)

    result = validate_dataset_assets(tmp_path, dataset_id, check_run_eval_zh=False)
    assert result.ok
    assert result.issue_count == 0


def test_validate_dataset_assets_reports_duplicate_ids(tmp_path: Path):
    dataset_id = "thchs30_noise_white"
    cut, _ = _write_lca_features(
        tmp_path / dataset_id,
        dataset_id,
        actual_num_frames=100,
        cut_id="dup-cut",
    )
    cuts = CutSet.from_cuts([cut, cut])
    _write_dataset(tmp_path, dataset_id, cuts)

    result = validate_dataset_assets(tmp_path, dataset_id, check_run_eval_zh=False)
    assert not result.ok
    assert any("duplicate cut id" in issue for issue in result.issues)


def test_validate_dataset_assets_reports_thchs30_noise_pointer_artifact(tmp_path: Path):
    dataset_id = "thchs30_noise_white"
    cut, _ = _write_lca_features(
        tmp_path / dataset_id,
        dataset_id,
        actual_num_frames=100,
    )
    supervision = fastcopy(
        cut.supervisions[0],
        text="data d11 750 wav trn",
        custom={"raw_text": "../data/D11_750.wav.trn"},
    )
    cut = fastcopy(cut, supervisions=[supervision])
    _write_dataset(tmp_path, dataset_id, CutSet.from_cuts([cut]))

    result = validate_dataset_assets(tmp_path, dataset_id, check_run_eval_zh=False)
    assert not result.ok
    assert any(
        "THCHS30 transcript pointer artifact detected" in issue
        for issue in result.issues
    )


def test_validate_dataset_assets_reports_thchs30_test_pointer_artifact(tmp_path: Path):
    dataset_id = "thchs30_test"
    cut, _ = _write_lca_features(
        tmp_path / dataset_id,
        dataset_id,
        actual_num_frames=100,
    )
    supervision = fastcopy(
        cut.supervisions[0],
        text="data d11 750 wav trn",
        custom={"raw_text": "../data/D11_750.wav.trn"},
    )
    cut = fastcopy(cut, supervisions=[supervision])
    _write_dataset(tmp_path, dataset_id, CutSet.from_cuts([cut]))

    result = validate_dataset_assets(tmp_path, dataset_id, check_run_eval_zh=False)
    assert not result.ok
    assert any(
        "THCHS30 transcript pointer artifact detected" in issue
        for issue in result.issues
    )


def test_validate_dataset_assets_reports_external_storage_and_shape_mismatch(
    tmp_path: Path,
):
    dataset_id = "ALIMEETING_TEST_NEAR_FIELD"
    foreign_root = tmp_path / "legacy_alimeeting_test_near"
    cut, _ = _write_lca_features(
        tmp_path / dataset_id,
        dataset_id,
        actual_num_frames=98,
        manifest_num_frames=98,
        cut_num_frames=100,
        storage_dataset_root=foreign_root,
    )
    cuts = CutSet.from_cuts([cut])
    _write_dataset(tmp_path, dataset_id, cuts)
    local_lca = tmp_path / dataset_id / "fbank" / f"{dataset_id}_feats.lca"
    local_lca.touch()

    result = validate_dataset_assets(tmp_path, dataset_id, check_run_eval_zh=False)
    assert not result.ok
    assert any("storage path escaped dataset fbank root" in issue for issue in result.issues)
    assert any("storage path mismatch" in issue for issue in result.issues)
    assert any("manifest num_frames mismatch" in issue for issue in result.issues)
    assert any("feature shape mismatch" in issue for issue in result.issues)


def _assert_external_storage_is_accepted_for_relaxed_gigaspeech_dataset(
    tmp_path: Path, dataset_id: str
):
    foreign_root = tmp_path / f"shared-{dataset_id}"
    cut, external_lca = _write_lca_features(
        tmp_path / dataset_id,
        dataset_id,
        actual_num_frames=100,
        storage_dataset_root=foreign_root,
    )
    cuts = CutSet.from_cuts([cut])
    dataset_root = _write_dataset(tmp_path, dataset_id, cuts)
    _link_prepared_lca(dataset_root, dataset_id, external_lca)

    result = validate_dataset_assets(tmp_path, dataset_id, check_run_eval_zh=False)

    assert result.ok
    assert result.issue_count == 0


def test_validate_dataset_assets_accepts_external_storage_for_relaxed_gigaspeech_dev(
    tmp_path: Path,
):
    _assert_external_storage_is_accepted_for_relaxed_gigaspeech_dataset(
        tmp_path, "GIGASPEECH_V1.0.0_DEV"
    )


def test_validate_dataset_assets_accepts_external_storage_for_relaxed_gigaspeech_test(
    tmp_path: Path,
):
    _assert_external_storage_is_accepted_for_relaxed_gigaspeech_dataset(
        tmp_path, "GIGASPEECH_V1.0.0_TEST"
    )


def test_validate_dataset_assets_keeps_external_storage_strict_for_other_datasets(
    tmp_path: Path,
):
    dataset_id = "ALIMEETING_TEST_NEAR_FIELD"
    foreign_root = tmp_path / "shared-alimeeting-test-near"
    cut, external_lca = _write_lca_features(
        tmp_path / dataset_id,
        dataset_id,
        actual_num_frames=100,
        storage_dataset_root=foreign_root,
    )
    cuts = CutSet.from_cuts([cut])
    dataset_root = _write_dataset(tmp_path, dataset_id, cuts)
    _link_prepared_lca(dataset_root, dataset_id, external_lca)

    result = validate_dataset_assets(tmp_path, dataset_id, check_run_eval_zh=False)

    assert not result.ok
    assert any("storage path escaped dataset fbank root" in issue for issue in result.issues)


def _assert_recording_level_features_are_accepted_for_relaxed_gigaspeech_dataset(
    tmp_path: Path, dataset_id: str
):
    foreign_root = tmp_path / f"recording-level-{dataset_id}"
    cut, external_lca = _write_lca_features(
        tmp_path / dataset_id,
        dataset_id,
        actual_num_frames=120,
        manifest_num_frames=120,
        cut_num_frames=80,
        storage_dataset_root=foreign_root,
    )
    dataset_root = _write_dataset(tmp_path, dataset_id, CutSet.from_cuts([cut]))
    _link_prepared_lca(dataset_root, dataset_id, external_lca)

    fake_cut = _FakeCut(
        id="recording-level-cut",
        duration=0.8,
        num_frames=None,
        features=_FakeFeatures(storage_path=str(external_lca), num_frames=120),
        loaded_num_frames=120,
    )
    with patch.object(
        validate_bench_assets_module,
        "load_manifest_lazy_or_eager",
        return_value=[fake_cut],
    ):
        result = validate_dataset_assets(tmp_path, dataset_id, check_run_eval_zh=False)

    assert result.ok
    assert result.issue_count == 0


def test_validate_dataset_assets_accepts_recording_level_features_for_relaxed_gigaspeech_dev(
    tmp_path: Path,
):
    _assert_recording_level_features_are_accepted_for_relaxed_gigaspeech_dataset(
        tmp_path, "GIGASPEECH_V1.0.0_DEV"
    )


def test_validate_dataset_assets_accepts_recording_level_features_for_relaxed_gigaspeech_test(
    tmp_path: Path,
):
    _assert_recording_level_features_are_accepted_for_relaxed_gigaspeech_dataset(
        tmp_path, "GIGASPEECH_V1.0.0_TEST"
    )


def test_validate_dataset_assets_checks_run_eval_zh_preflight(tmp_path: Path):
    dataset_id = "thchs30_test"
    cuts = CutSet.from_cuts(
        [
            _write_lca_features(
                tmp_path / dataset_id,
                dataset_id,
                actual_num_frames=10,
                cut_id=f"cut-{index}",
            )[0]
            for index in range(11)
        ]
    )
    _write_dataset(tmp_path, dataset_id, cuts)

    result = validate_dataset_assets(tmp_path, dataset_id)
    assert result.ok
    assert result.run_eval_zh_checked
    assert result.run_eval_zh_ok is True


def test_validate_dataset_assets_reports_run_eval_zh_incompatible_short_cuts(
    tmp_path: Path,
):
    dataset_id = "thchs30_test"
    cuts = CutSet.from_cuts(
        [
            _write_lca_features(
                tmp_path / dataset_id,
                dataset_id,
                actual_num_frames=8,
                cut_id=f"cut-{index}",
            )[0]
            for index in range(11)
        ]
    )
    _write_dataset(tmp_path, dataset_id, cuts)

    result = validate_dataset_assets(tmp_path, dataset_id)
    assert not result.ok
    assert result.run_eval_zh_checked
    assert result.run_eval_zh_ok is False
    assert any("run_eval_zh preflight removed all cuts" in issue for issue in result.issues)


def test_write_available_dataset_summary_outputs_minimal_fields(tmp_path: Path):
    output_path = tmp_path / "metadata" / "available_datasets_min.json"
    results = [
        DatasetValidationResult(
            dataset_id="thchs30_test",
            language="zh",
            language_label="中文",
            raw_cuts_path="/bench/thchs30_test/raw_cuts/thchs30_test_cuts_raw.jsonl.gz",
            cuts_path="/bench/thchs30_test/fbank/thchs30_test_cuts.jsonl.gz",
            lca_path="/bench/thchs30_test/fbank/thchs30_test_feats.lca",
        ),
        DatasetValidationResult(
            dataset_id="GIGASPEECH_V1.0.0_DEV",
            language="en",
            language_label="英文",
            raw_cuts_path="/bench/GIGASPEECH_V1.0.0_DEV/raw_cuts/GIGASPEECH_V1.0.0_DEV_cuts_raw.jsonl.gz",
            cuts_path="/bench/GIGASPEECH_V1.0.0_DEV/fbank/GIGASPEECH_V1.0.0_DEV_cuts.jsonl.gz",
            lca_path="/bench/GIGASPEECH_V1.0.0_DEV/fbank/GIGASPEECH_V1.0.0_DEV_feats.lca",
            issue_count=1,
            issues=["synthetic validation failure"],
        ),
    ]

    write_available_dataset_summary(results, output_path)
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload == [
        {
            "dataset_id": "GIGASPEECH_V1.0.0_DEV",
            "language": "英文",
            "feature_path": "/bench/GIGASPEECH_V1.0.0_DEV/fbank/GIGASPEECH_V1.0.0_DEV_cuts.jsonl.gz",
            "validation_success": False,
        },
        {
            "dataset_id": "thchs30_test",
            "language": "中文",
            "feature_path": "/bench/thchs30_test/fbank/thchs30_test_cuts.jsonl.gz",
            "validation_success": True,
        },
    ]


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        test_thchs_noise_label_uses_noise_root_relative_path(Path(tmpdir))
    with tempfile.TemporaryDirectory() as tmpdir:
        test_load_thchs30_noise_transcript_resolves_pointer_file(Path(tmpdir))
    with tempfile.TemporaryDirectory() as tmpdir:
        test_load_thchs30_transcript_resolves_pointer_file(Path(tmpdir))
    with tempfile.TemporaryDirectory() as tmpdir:
        test_build_thchs30_subset_manifests_resolves_pointer_transcript_for_thchs30_test(
            Path(tmpdir)
        )
    with tempfile.TemporaryDirectory() as tmpdir:
        test_load_transcript_keeps_existing_single_line_behavior(Path(tmpdir))
    test_voxpopuli_recording_id_strips_language_suffix()
    with tempfile.TemporaryDirectory() as tmpdir:
        test_build_voxpopuli_accented_test_manifests_uses_dedicated_annotations(
            Path(tmpdir)
        )
    test_align_trimmed_single_supervision_durations_repairs_tiny_float_drift()
    test_align_trimmed_single_supervision_durations_keeps_non_trimmed_cuts_strict()
    test_align_trimmed_single_supervision_durations_keeps_large_drift_strict()
    test_align_cutset_to_feature_durations_repairs_tiny_drift()
    test_align_cutset_to_feature_durations_keeps_large_drift_strict()
    with tempfile.TemporaryDirectory() as tmpdir:
        test_validate_dataset_assets_reports_thchs30_test_pointer_artifact(Path(tmpdir))
    with tempfile.TemporaryDirectory() as tmpdir:
        test_validate_dataset_assets_accepts_valid_local_storage(Path(tmpdir))
    with tempfile.TemporaryDirectory() as tmpdir:
        test_validate_dataset_assets_accepts_valid_local_sharded_storage(Path(tmpdir))
    with tempfile.TemporaryDirectory() as tmpdir:
        test_validate_dataset_assets_reports_duplicate_ids(Path(tmpdir))
    with tempfile.TemporaryDirectory() as tmpdir:
        test_validate_dataset_assets_reports_thchs30_noise_pointer_artifact(Path(tmpdir))
    with tempfile.TemporaryDirectory() as tmpdir:
        test_validate_dataset_assets_reports_external_storage_and_shape_mismatch(
            Path(tmpdir)
        )
    with tempfile.TemporaryDirectory() as tmpdir:
        test_validate_dataset_assets_accepts_external_storage_for_relaxed_gigaspeech_dev(
            Path(tmpdir)
        )
    with tempfile.TemporaryDirectory() as tmpdir:
        test_validate_dataset_assets_accepts_external_storage_for_relaxed_gigaspeech_test(
            Path(tmpdir)
        )
    with tempfile.TemporaryDirectory() as tmpdir:
        test_validate_dataset_assets_keeps_external_storage_strict_for_other_datasets(
            Path(tmpdir)
        )
    with tempfile.TemporaryDirectory() as tmpdir:
        test_validate_dataset_assets_accepts_recording_level_features_for_relaxed_gigaspeech_dev(
            Path(tmpdir)
        )
    with tempfile.TemporaryDirectory() as tmpdir:
        test_validate_dataset_assets_accepts_recording_level_features_for_relaxed_gigaspeech_test(
            Path(tmpdir)
        )
    with tempfile.TemporaryDirectory() as tmpdir:
        test_validate_dataset_assets_checks_run_eval_zh_preflight(Path(tmpdir))
    with tempfile.TemporaryDirectory() as tmpdir:
        test_validate_dataset_assets_reports_run_eval_zh_incompatible_short_cuts(
            Path(tmpdir)
        )
    with tempfile.TemporaryDirectory() as tmpdir:
        test_write_available_dataset_summary_outputs_minimal_fields(Path(tmpdir))
