#!/usr/bin/env python3

import argparse
import gzip
import json
import re
from collections import Counter
from pathlib import Path

import soundfile as sf

WAV_RE = re.compile(
    r"^EN/EN_P\d{6}/EN_P\d{6}_S\d{5}/flac/"
    r"EN_P\d{6}_S\d{5}_W\d{8}(?:_V\d{4})?\.flac$"
)


def get_args():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("--sample-root", type=Path, required=True)
    return parser.parse_args()


def read_jsonl_gz(path: Path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def main() -> None:
    args = get_args()
    manifest_dir = args.sample_root / "manifests" / "EN"
    segment_manifest = manifest_dir / "jellycat_EN_segments.sample.jsonl.gz"
    rejected_manifest = manifest_dir / "jellycat_EN_rejected.sample.jsonl.gz"
    recordings_manifest = manifest_dir / "jellycat_EN_recordings.sample.jsonl.gz"
    supervisions_manifest = manifest_dir / "jellycat_EN_supervisions.sample.jsonl.gz"

    required = [segment_manifest, rejected_manifest, recordings_manifest, supervisions_manifest]
    for path in required:
        if not path.is_file():
            raise FileNotFoundError(path)

    records = list(read_jsonl_gz(segment_manifest))
    if not records:
        raise AssertionError("segment manifest is empty")

    stats = Counter()
    for record in records:
        stats[f"source_language_{record['source_language']}"] += 1
        if record["language"] != "EN":
            raise AssertionError(f"unexpected language: {record}")
        wav_path = args.sample_root / record["wav"]
        if not wav_path.is_file():
            raise FileNotFoundError(wav_path)
        info = sf.info(wav_path)
        if info.samplerate != 24000:
            raise AssertionError(f"{wav_path} samplerate={info.samplerate}")
        if info.channels != 1:
            raise AssertionError(f"{wav_path} channels={info.channels}")
        if int(record["sampling_rate"]) != info.samplerate:
            raise AssertionError(f"{wav_path} manifest sampling_rate={record['sampling_rate']}")
        if int(record["num_samples"]) != info.frames:
            raise AssertionError(
                f"{wav_path} manifest num_samples={record['num_samples']}, frames={info.frames}"
            )
        if float(record["duration"]) != int(record["num_samples"]) / int(record["sampling_rate"]):
            raise AssertionError(f"{wav_path} duration is not derived from num_samples/sample_rate")
        if abs(info.duration - float(record["duration"])) > 1e-9:
            raise AssertionError(
                f"{wav_path} duration={info.duration:.3f}, manifest={record['duration']:.3f}"
            )
        if not WAV_RE.fullmatch(record["wav"]):
            raise AssertionError(f"unexpected wav layout: {record['wav']}")
        parts = Path(record["wav"]).parts
        if record["podcast"] != parts[1]:
            raise AssertionError(f"podcast id does not match path: {record}")
        if record["speaker"] != parts[2]:
            raise AssertionError(f"speaker id does not match path: {record}")
        if record["id"] != Path(record["wav"]).stem:
            raise AssertionError(f"id does not match filename: {record}")
        for key in ("source_manifest_id", "source_podcast_hash", "source_episode_hash"):
            if not record.get(key):
                raise AssertionError(f"missing source metadata {key}: {record}")

    rejected = list(read_jsonl_gz(rejected_manifest))

    recordings = list(read_jsonl_gz(recordings_manifest))
    supervisions = list(read_jsonl_gz(supervisions_manifest))
    if len(recordings) != len(records):
        raise AssertionError(f"recordings={len(recordings)} records={len(records)}")
    if len(supervisions) != len(records):
        raise AssertionError(f"supervisions={len(supervisions)} records={len(records)}")
    record_by_id = {record["id"]: record for record in records}
    for recording in recordings:
        manifest_record = record_by_id[recording["id"]]
        if int(recording["num_samples"]) != int(manifest_record["num_samples"]):
            raise AssertionError(f"{recording['id']} Recording.num_samples mismatch")
        expected_duration = int(manifest_record["num_samples"]) / int(manifest_record["sampling_rate"])
        if float(recording["duration"]) != expected_duration:
            raise AssertionError(f"{recording['id']} Recording.duration mismatch")
    for supervision in supervisions:
        manifest_record = record_by_id[supervision["id"]]
        expected_duration = int(manifest_record["num_samples"]) / int(manifest_record["sampling_rate"])
        if float(supervision["start"]) != 0.0 or float(supervision["duration"]) != expected_duration:
            raise AssertionError(f"{supervision['id']} Supervision duration mismatch")

    summary = {
        "status": "validated",
        "sample_root": str(args.sample_root),
        "segments": len(records),
        "rejected": len(rejected),
        "stats": dict(stats),
        "segment_manifest": str(segment_manifest),
        "rejected_manifest": str(rejected_manifest),
    }
    summary_path = manifest_dir / "validation_summary.json"
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
