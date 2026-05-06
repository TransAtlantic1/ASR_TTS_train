#!/usr/bin/env python3

import argparse
import contextlib
import io
import json
import sys
import tempfile
import time
from multiprocessing import Process, Queue
from pathlib import Path


DEFAULT_VIBEVOICE_ROOT = Path(
    "/inspire/hdd/project/embodied-multimodality/chenxie-25019/zhikang/codes/VibeVoice"
)


def get_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description=(
            "Call an existing VibeVoice vLLM ASR service for Jellycat VAD child "
            "audio listed in a text file. Writes VibeVoice-style sidecar JSON "
            "next to each child FLAC. Does not modify the VibeVoice repository."
        ),
    )
    parser.add_argument("--audio-list", type=Path, required=True)
    parser.add_argument("--vibevoice-root", type=Path, default=DEFAULT_VIBEVOICE_ROOT)
    parser.add_argument("--url", action="append", default=None)
    parser.add_argument("--workers-per-url", type=int, default=32)
    parser.add_argument("--hotwords", default=None)
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--max-records", type=int, default=-1)
    parser.add_argument("--summary-output", type=Path, default=None)
    return parser.parse_args()


def load_vibevoice_helper(vibevoice_root: Path):
    tests_dir = vibevoice_root / "vllm_plugin" / "tests"
    if not (tests_dir / "test_api_auto_recover.py").is_file():
        raise FileNotFoundError(tests_dir / "test_api_auto_recover.py")
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(tests_dir))
    from test_api_auto_recover import test_transcription_with_recovery

    return test_transcription_with_recovery


def iter_audio_list(path: Path, max_records: int) -> list[Path]:
    output = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            item = line.strip()
            if not item:
                continue
            output.append(Path(item))
            if max_records > 0 and len(output) >= max_records:
                break
    return output


def to_standard_format(audio_path: Path, raw_text: str, generation_time: float) -> dict:
    segments_raw = json.loads(raw_text)
    segments = []
    for raw_seg in segments_raw:
        segment = {
            "start_time": raw_seg["Start"],
            "end_time": raw_seg["End"],
            "text": raw_seg["Content"],
        }
        if "Speaker" in raw_seg:
            segment["speaker_id"] = raw_seg["Speaker"]
        segments.append(segment)
    return {
        "file": str(audio_path),
        "generation_time": generation_time,
        "segments": segments,
    }


def transcribe_one(
    *,
    audio_path: Path,
    url: str,
    helper,
    skip_existing: bool,
    hotwords: str | None,
    debug: bool,
) -> str:
    output_path = audio_path.with_suffix(".json")
    if skip_existing and output_path.is_file():
        return "skipped_existing"

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        start = time.perf_counter()
        with contextlib.redirect_stdout(io.StringIO()):
            helper(
                audio_path=str(audio_path),
                output_path=str(tmp_path),
                base_url=url,
                hotwords=hotwords,
                debug=debug,
            )
        elapsed = time.perf_counter() - start
        raw_text = tmp_path.read_text(encoding="utf-8").strip()
        result = to_standard_format(audio_path, raw_text, elapsed)
        output_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return "transcribed"
    finally:
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink()


def worker_process(
    *,
    work_queue: Queue,
    result_queue: Queue,
    url: str,
    vibevoice_root: Path,
    skip_existing: bool,
    hotwords: str | None,
    debug: bool,
) -> None:
    helper = load_vibevoice_helper(vibevoice_root)
    while True:
        audio_path = work_queue.get()
        if audio_path is None:
            return
        try:
            status = transcribe_one(
                audio_path=audio_path,
                url=url,
                helper=helper,
                skip_existing=skip_existing,
                hotwords=hotwords,
                debug=debug,
            )
            result_queue.put({"status": status, "file": str(audio_path)})
        except Exception as exc:
            result_queue.put(
                {"status": "failed", "file": str(audio_path), "error": repr(exc)}
            )


def main() -> None:
    args = get_args()
    urls = args.url or ["http://localhost:8000"]
    audio_paths = iter_audio_list(args.audio_list, args.max_records)
    num_workers = len(urls) * args.workers_per_url
    if num_workers <= 0:
        raise ValueError("--workers-per-url must be positive")

    work_queue: Queue = Queue(maxsize=max(1, num_workers * 4))
    result_queue: Queue = Queue()

    workers = [
        Process(
            target=worker_process,
            kwargs={
                "work_queue": work_queue,
                "result_queue": result_queue,
                "url": url,
                "vibevoice_root": args.vibevoice_root,
                "skip_existing": args.skip_existing,
                "hotwords": args.hotwords,
                "debug": args.debug,
            },
        )
        for url in urls
        for _ in range(args.workers_per_url)
    ]
    for process in workers:
        process.start()

    for path in audio_paths:
        work_queue.put(path)
    for _ in range(num_workers):
        work_queue.put(None)

    stats = {"total": len(audio_paths), "transcribed": 0, "skipped_existing": 0, "failed": 0}
    failures = []
    for _ in audio_paths:
        result = result_queue.get()
        status = result["status"]
        stats[status] = stats.get(status, 0) + 1
        if status == "failed" and len(failures) < 20:
            failures.append(
                {"file": result.get("file"), "error": result.get("error", "unknown")}
            )

    for process in workers:
        process.join()

    summary = {
        "audio_list": str(args.audio_list),
        "vibevoice_root": str(args.vibevoice_root),
        "urls": urls,
        "workers_per_url": args.workers_per_url,
        "stats": stats,
        "failures": failures,
    }
    if args.summary_output is not None:
        args.summary_output.parent.mkdir(parents=True, exist_ok=True)
        args.summary_output.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
