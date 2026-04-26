#!/usr/bin/env python3

import json
import math
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import torch
import torchaudio
from lhotse import AudioSource, CutSet, LilcomChunkyWriter, MonoCut, Recording
from lhotse.audio import AudioLoadingError
from lhotse.qa import validate_features

import compute_emilia_precomputed_features as compute_mod
from compute_emilia_precomputed_features import (
    compute_and_store_features_batch_checked,
    compute_features_grouped_by_sampling_rate,
    report_path_for_output,
    shard_idx_from_output_path,
)
from f5tts_mel_extractor import F5TTSMelConfig, F5TTSMelExtractor


def make_sine_wave(sample_rate: int, duration: float = 0.25) -> torch.Tensor:
    num_samples = int(sample_rate * duration)
    t = torch.arange(num_samples, dtype=torch.float32) / sample_rate
    return torch.sin(2 * math.pi * 440.0 * t)


def make_cut(cut_id: str, sampling_rate: int) -> MonoCut:
    duration = 1.0
    recording = Recording(
        id=cut_id,
        sources=[
            AudioSource(type="file", channels=[0], source=f"/data/{cut_id}.wav")
        ],
        sampling_rate=sampling_rate,
        num_samples=int(duration * sampling_rate),
        duration=duration,
    )
    return MonoCut(
        id=cut_id,
        start=0.0,
        duration=duration,
        channel=0,
        supervisions=[],
        recording=recording,
    )


def test_compute_features_grouped_by_sampling_rate_splits_mixed_rate_shard_and_preserves_order():
    cut_set = CutSet.from_cuts(
        [
            make_cut("cut-32000-a", 32000),
            make_cut("cut-24000-a", 24000),
            make_cut("cut-32000-b", 32000),
            make_cut("cut-24000-b", 24000),
        ]
    )
    original_order = [cut.id for cut in cut_set]
    calls = []

    def fake_compute_and_store_features_batch(
        cut_set,
        extractor,
        storage_path,
        batch_duration,
        num_workers,
        storage_type,
        overwrite,
    ):
        cuts = list(cut_set)
        calls.append(
            {
                "ids": [cut.id for cut in cuts],
                "sampling_rates": sorted({cut.sampling_rate for cut in cuts}),
                "storage_path": storage_path,
                "num_workers": num_workers,
                "batch_duration": batch_duration,
                "storage_type": storage_type.__name__,
                "overwrite": overwrite,
            }
        )
        return CutSet.from_cuts(reversed(cuts))

    with patch.object(
        compute_mod,
        "compute_and_store_features_batch_checked",
        new=fake_compute_and_store_features_batch,
    ):
        computed = compute_features_grouped_by_sampling_rate(
            cut_set=cut_set,
            extractor=object(),
            storage_path="/tmp/test-storage",
            num_workers=7,
            batch_duration=2000.0,
        )

    assert [cut.id for cut in computed] == original_order
    assert len(calls) == 2
    assert calls[0]["sampling_rates"] == [24000]
    assert calls[0]["ids"] == ["cut-24000-a", "cut-24000-b"]
    assert calls[0]["overwrite"] is True
    assert calls[1]["sampling_rates"] == [32000]
    assert calls[1]["ids"] == ["cut-32000-a", "cut-32000-b"]
    assert calls[1]["overwrite"] is False
    assert all(call["storage_path"] == "/tmp/test-storage" for call in calls)
    assert all(call["num_workers"] == 7 for call in calls)
    assert all(call["batch_duration"] == 2000.0 for call in calls)
    assert all(call["storage_type"] == "LilcomChunkyWriter" for call in calls)


def test_compute_features_grouped_by_sampling_rate_skips_missing_cuts_and_writes_report():
    cut_a = make_cut("cut-a", 24000)
    cut_b = make_cut("cut-b", 24000)
    cut_c = make_cut("cut-c", 24000)
    cut_set = CutSet.from_cuts([cut_a, cut_b, cut_c])

    with TemporaryDirectory() as tmpdir:
        output_cuts_path = Path(tmpdir) / "emilia_en_cuts_train.0007.jsonl.gz"
        raw_cuts_path = Path(tmpdir) / "emilia_en_cuts_train_raw.0007.jsonl.gz"
        report_dir = Path(tmpdir) / "bad-cuts"

        def fake_compute_and_store_features_batch(
            cut_set,
            extractor,
            storage_path,
            batch_duration,
            num_workers,
            storage_type,
            overwrite,
        ):
            return CutSet.from_cuts([cut_a, cut_c])

        def fake_load_audio(self):
            if self.id == "cut-b":
                raise AudioLoadingError("bad audio for cut-b")
            return None

        with patch.object(
            compute_mod,
            "compute_and_store_features_batch_checked",
            new=fake_compute_and_store_features_batch,
        ), patch.object(MonoCut, "load_audio", new=fake_load_audio):
            computed = compute_features_grouped_by_sampling_rate(
                cut_set=cut_set,
                extractor=object(),
                storage_path=str(Path(tmpdir) / "storage"),
                num_workers=4,
                batch_duration=1000.0,
                skip_missing_cuts=True,
                raw_cuts_path=raw_cuts_path,
                output_cuts_path=output_cuts_path,
                bad_cut_report_dir=report_dir,
            )

        assert [cut.id for cut in computed] == ["cut-a", "cut-c"]
        report_path = report_path_for_output(output_cuts_path, report_dir)
        assert report_path.is_file()
        records = [json.loads(line) for line in report_path.read_text().splitlines()]
        assert len(records) == 1
        assert records[0]["cut_id"] == "cut-b"
        assert records[0]["reason_type"] == "AudioLoadingError"
        assert records[0]["raw_cuts_path"] == str(raw_cuts_path)
        assert records[0]["output_cuts_path"] == str(output_cuts_path)


def test_compute_features_grouped_by_sampling_rate_skips_unknown_missing_cut_reason():
    cut_a = make_cut("cut-a", 24000)
    cut_b = make_cut("cut-b", 24000)
    cut_set = CutSet.from_cuts([cut_a, cut_b])

    with TemporaryDirectory() as tmpdir:
        output_cuts_path = Path(tmpdir) / "emilia_en_cuts_train.0008.jsonl.gz"
        report_dir = Path(tmpdir) / "bad-cuts"

        def fake_compute_and_store_features_batch(
            cut_set,
            extractor,
            storage_path,
            batch_duration,
            num_workers,
            storage_type,
            overwrite,
        ):
            return CutSet.from_cuts([cut_a])

        with patch.object(
            compute_mod,
            "compute_and_store_features_batch_checked",
            new=fake_compute_and_store_features_batch,
        ), patch.object(MonoCut, "load_audio", return_value=None):
            computed = compute_features_grouped_by_sampling_rate(
                cut_set=cut_set,
                extractor=object(),
                storage_path=str(Path(tmpdir) / "storage"),
                num_workers=2,
                batch_duration=500.0,
                skip_missing_cuts=True,
                raw_cuts_path=Path(tmpdir) / "raw.jsonl.gz",
                output_cuts_path=output_cuts_path,
                bad_cut_report_dir=report_dir,
            )

        assert [cut.id for cut in computed] == ["cut-a"]
        report_path = report_path_for_output(output_cuts_path, report_dir)
        records = [json.loads(line) for line in report_path.read_text().splitlines()]
        assert records[0]["cut_id"] == "cut-b"
        assert records[0]["reason_type"] == "MissingAfterBatch"


def test_compute_features_grouped_by_sampling_rate_fails_fast_when_batch_returns_none():
    cut_a = make_cut("cut-a", 24000)
    cut_set = CutSet.from_cuts([cut_a])

    with TemporaryDirectory() as tmpdir:
        output_cuts_path = Path(tmpdir) / "emilia_en_cuts_train.0009.jsonl.gz"
        raw_cuts_path = Path(tmpdir) / "emilia_en_cuts_train_raw.0009.jsonl.gz"

        with patch.object(
            compute_mod,
            "compute_and_store_features_batch_checked",
            return_value=None,
        ):
            try:
                compute_features_grouped_by_sampling_rate(
                    cut_set=cut_set,
                    extractor=object(),
                    storage_path=str(Path(tmpdir) / "storage"),
                    num_workers=2,
                    batch_duration=500.0,
                    skip_missing_cuts=True,
                    raw_cuts_path=raw_cuts_path,
                    output_cuts_path=output_cuts_path,
                )
            except RuntimeError as ex:
                message = str(ex)
            else:
                raise AssertionError("Expected RuntimeError when feature batch returns None")

        assert "returned None" in message
        assert "shard=0009" in message
        assert "sampling_rate_batch_idx=0" in message
        assert "batch_duration=500.0" in message
        assert "first_cut_id=cut-a" in message
        assert str(raw_cuts_path) in message
        assert str(output_cuts_path) in message


def test_checked_batch_writer_uses_feature_sampling_rate_for_32k_input():
    sample_rate = 32000
    duration = 0.25
    waveform = make_sine_wave(sample_rate, duration).unsqueeze(0)

    with TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        wav_path = tmpdir / "cut-32k.wav"
        torchaudio.save(str(wav_path), waveform, sample_rate)
        recording = Recording.from_file(wav_path, recording_id="cut-32k")
        cut_set = CutSet.from_cuts(
            [
                MonoCut(
                    id="cut-32k",
                    start=0.0,
                    duration=recording.duration,
                    channel=0,
                    supervisions=[],
                    recording=recording,
                )
            ]
        )
        extractor = F5TTSMelExtractor(F5TTSMelConfig(device="cpu"))

        computed = compute_and_store_features_batch_checked(
            cut_set=cut_set,
            extractor=extractor,
            storage_path=str(tmpdir / "feats"),
            batch_duration=10.0,
            num_workers=0,
            storage_type=LilcomChunkyWriter,
            overwrite=True,
        )

        cut = next(iter(computed))
        assert cut.recording.sampling_rate == 32000
        assert cut.features.sampling_rate == 24000
        validate_features(cut.features, feats_data=cut.load_features())


def test_checked_batch_writer_exposes_save_worker_exceptions():
    sample_rate = 24000
    waveform = make_sine_wave(sample_rate, 0.1).unsqueeze(0)

    with TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        wav_path = tmpdir / "cut.wav"
        torchaudio.save(str(wav_path), waveform, sample_rate)
        recording = Recording.from_file(wav_path, recording_id="cut")
        cut_set = CutSet.from_cuts(
            [
                MonoCut(
                    id="cut",
                    start=0.0,
                    duration=recording.duration,
                    channel=0,
                    supervisions=[],
                    recording=recording,
                )
            ]
        )
        extractor = F5TTSMelExtractor(F5TTSMelConfig(device="cpu"))

        with patch.object(
            compute_mod,
            "validate_features",
            side_effect=RuntimeError("save worker validation failed"),
        ):
            try:
                compute_and_store_features_batch_checked(
                    cut_set=cut_set,
                    extractor=extractor,
                    storage_path=str(tmpdir / "feats"),
                    batch_duration=10.0,
                    num_workers=0,
                    storage_type=LilcomChunkyWriter,
                    overwrite=True,
                )
            except RuntimeError as ex:
                message = str(ex)
                cause = str(ex.__cause__)
            else:
                raise AssertionError("Expected save worker exception to be exposed")

        assert "Feature save worker failed" in message
        assert "storage_path=" in message
        assert cause == "save worker validation failed"


def test_shard_idx_from_output_path():
    assert shard_idx_from_output_path(Path("emilia_en_cuts_train.0128.jsonl.gz")) == "0128"


if __name__ == "__main__":
    test_compute_features_grouped_by_sampling_rate_splits_mixed_rate_shard_and_preserves_order()
    test_compute_features_grouped_by_sampling_rate_skips_missing_cuts_and_writes_report()
    test_compute_features_grouped_by_sampling_rate_skips_unknown_missing_cut_reason()
    test_compute_features_grouped_by_sampling_rate_fails_fast_when_batch_returns_none()
    test_checked_batch_writer_uses_feature_sampling_rate_for_32k_input()
    test_checked_batch_writer_exposes_save_worker_exceptions()
    test_shard_idx_from_output_path()
    print("ok")
