#!/usr/bin/env python3

from pathlib import Path
from unittest.mock import patch

from lhotse import AudioSource, Recording, RecordingSet

from build_emilia_stage4_cuts import iter_fixed_recordings, write_fixed_recordings


def make_file_recording(
    recording_id: str,
    source_path: str,
    duration: float,
    sampling_rate: int = 24000,
) -> Recording:
    return Recording(
        id=recording_id,
        sources=[AudioSource(type="file", channels=[0], source=source_path)],
        sampling_rate=sampling_rate,
        num_samples=int(duration * sampling_rate),
        duration=duration,
    )


def make_non_file_recording(
    recording_id: str,
    duration: float,
    sampling_rate: int = 16000,
) -> Recording:
    return Recording(
        id=recording_id,
        sources=[
            AudioSource(
                type="command",
                channels=[0],
                source=f"cat {recording_id}.wav",
            )
        ],
        sampling_rate=sampling_rate,
        num_samples=int(duration * sampling_rate),
        duration=duration,
    )


def test_write_fixed_recordings_preserves_order_across_probe_strategies(
    tmp_path: Path,
):
    recordings = RecordingSet.from_recordings(
        [
            make_file_recording(
                "utt-uniform",
                "/data/EN/EN_B00001/utt-uniform.mp3",
                duration=1.0,
                sampling_rate=16000,
            ),
            make_file_recording(
                "utt-probed",
                "/data/EN/EN_B00002/utt-probed.mp3",
                duration=1.0,
                sampling_rate=16000,
            ),
            make_non_file_recording("utt-reused", duration=0.5, sampling_rate=16000),
        ]
    )
    sample_rate_plan = {
        "EN_B00001": {
            "status": "uniform",
            "sample_rate_counts": {32000: 8},
        },
        "EN_B00002": {
            "status": "mixed",
            "sample_rate_counts": {24000: 4, 32000: 4},
        },
    }
    output_path = tmp_path / "fixed_recordings.jsonl.gz"

    with patch(
        "build_emilia_stage4_cuts.probe_audio_info",
        return_value=(24000, 24000),
    ) as patched_probe:
        stats = write_fixed_recordings(
            recordings=recordings,
            output_path=output_path,
            sample_rate_plan=sample_rate_plan,
            probe_num_workers=1,
            probe_chunksize=32,
        )

    fixed_manifest = RecordingSet.from_file(output_path)
    fixed = [] if fixed_manifest is None else list(fixed_manifest)

    assert [recording.id for recording in fixed] == [
        "utt-uniform",
        "utt-probed",
        "utt-reused",
    ]
    assert [recording.sampling_rate for recording in fixed] == [32000, 24000, 16000]
    assert stats["recordings_seen"] == 3
    assert stats["strategy_report_uniform_32000"] == 1
    assert stats["strategy_probed_24000"] == 1
    assert stats["strategy_reused_original"] == 1
    patched_probe.assert_called_once_with("/data/EN/EN_B00002/utt-probed.mp3")


def test_iter_fixed_recordings_uses_process_pool_for_parallel_probes():
    recordings = [
        make_file_recording(
            "utt-probed",
            "/data/EN/EN_B00002/utt-probed.mp3",
            duration=1.0,
            sampling_rate=16000,
        )
    ]
    sample_rate_plan = {
        "EN_B00002": {
            "status": "mixed",
            "sample_rate_counts": {24000: 4, 32000: 4},
        }
    }

    created_executors = []
    observed = {}

    class DummyExecutor:
        def __init__(self, max_workers: int):
            self.max_workers = max_workers
            self.shutdown_called = False

        def shutdown(self):
            self.shutdown_called = True

    def fake_map_probe_audio_info(
        source_paths,
        probe_num_workers,
        probe_chunksize,
        executor=None,
    ):
        observed["source_paths"] = list(source_paths)
        observed["probe_num_workers"] = probe_num_workers
        observed["probe_chunksize"] = probe_chunksize
        observed["executor"] = executor
        return iter([(32000, 32000)])

    def fake_process_pool_executor(max_workers: int):
        executor = DummyExecutor(max_workers=max_workers)
        created_executors.append(executor)
        return executor

    with patch(
        "build_emilia_stage4_cuts.ProcessPoolExecutor",
        side_effect=fake_process_pool_executor,
    ), patch(
        "build_emilia_stage4_cuts.map_probe_audio_info",
        side_effect=fake_map_probe_audio_info,
    ):
        fixed = list(
            iter_fixed_recordings(
                recordings=recordings,
                sample_rate_plan=sample_rate_plan,
                probe_num_workers=8,
                probe_chunksize=17,
            )
        )

    assert len(created_executors) == 1
    assert created_executors[0].max_workers == 8
    assert created_executors[0].shutdown_called is True
    assert observed["source_paths"] == ["/data/EN/EN_B00002/utt-probed.mp3"]
    assert observed["probe_num_workers"] == 8
    assert observed["probe_chunksize"] == 17
    assert observed["executor"] is created_executors[0]
    assert fixed[0][0].sampling_rate == 32000
    assert fixed[0][1] == "probed_32000"


if __name__ == "__main__":
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as d:
        test_write_fixed_recordings_preserves_order_across_probe_strategies(
            Path(d)
        )
    test_iter_fixed_recordings_uses_process_pool_for_parallel_probes()
    print("ok")
