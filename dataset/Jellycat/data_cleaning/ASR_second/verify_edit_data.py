from __future__ import annotations

import argparse
import base64
import gzip
import json
import logging
import os
import re
import threading
import time
import unicodedata
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from itertools import cycle
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence

try:
    import jiwer
except ImportError:  # pragma: no cover - reported by --dry-run.
    jiwer = None

try:
    import requests
except ImportError:  # pragma: no cover - reported by --dry-run.
    requests = None

try:
    from pypinyin import Style, lazy_pinyin
except ImportError:  # pragma: no cover - reported by --dry-run.
    Style = None
    lazy_pinyin = None

try:
    from qwen_asr import parse_asr_output as qwen_parse_asr_output
except ImportError:  # pragma: no cover - service output may already be text.
    qwen_parse_asr_output = None

try:
    from opencc import OpenCC
except ImportError:  # pragma: no cover - checked before Chinese scoring.
    OpenCC = None

try:
    import zhconv
except ImportError:  # pragma: no cover - checked before Chinese scoring.
    zhconv = None

try:
    from tqdm import tqdm
except ImportError:  # pragma: no cover - fallback keeps script runnable.
    tqdm = None


DEFAULT_AUDIO_ROOT = (
    "/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/"
    "zhikang/Jellycat"
)
DEFAULT_PORTS = os.environ.get("PORTS", "8000")

ZH_ALIASES = {
    "zh",
    "zh-cn",
    "zh_ch",
    "zh-ch",
    "zh-hans",
    "zh-tw",
    "zh-yue",
    "zh-yue-hk",
}
EN_ALIASES = {"en", "en-us"}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("verify_edit_data")

_OPENCC_CONVERTER = None


def parse_ports(value: str) -> List[int]:
    ports = [p.strip() for p in value.replace(",", " ").split() if p.strip()]
    if not ports:
        raise ValueError("At least one ASR port is required")
    return [int(p) for p in ports]


def open_text(path: Path):
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8")
    return path.open("r", encoding="utf-8")


def iter_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    with open_text(path) as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no}: invalid JSON") from exc


def normalize_lang(value: Any) -> Optional[str]:
    lang = str(value or "").strip().replace("_", "-").lower()
    if lang in ZH_ALIASES or lang.upper() == "ZH":
        return "zh"
    if lang in EN_ALIASES or lang.upper() == "EN":
        return "en"
    return None


def resolve_audio_path(wav: str, audio_root: Path) -> Path:
    wav_path = Path(wav)
    if wav_path.is_absolute():
        return wav_path
    return audio_root / wav_path


def simplify_zh(text: str) -> str:
    global _OPENCC_CONVERTER
    if OpenCC is not None:
        if _OPENCC_CONVERTER is None:
            _OPENCC_CONVERTER = OpenCC("t2s")
        return _OPENCC_CONVERTER.convert(text)
    if zhconv is not None:
        return zhconv.convert(text, "zh-cn")
    raise RuntimeError("Chinese CER requires opencc or zhconv, but neither is available")


def is_punct_or_symbol(ch: str) -> bool:
    return unicodedata.category(ch).startswith(("P", "S"))


def normalize_zh_chars(text: str) -> str:
    text = simplify_zh(text)
    return "".join(ch for ch in text if not ch.isspace() and not is_punct_or_symbol(ch))


def normalize_en(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^\w\s']", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def zh_pinyin_tone3(text: str) -> str:
    if lazy_pinyin is None or Style is None:
        raise RuntimeError("Chinese pinyin WER requires pypinyin")
    chars = normalize_zh_chars(text)
    return " ".join(lazy_pinyin(chars, style=Style.TONE3, neutral_tone_with_five=True))


def alignment_edits(out: Any) -> List[Dict[str, str]]:
    ref_w, hyp_w = out.references[0], out.hypotheses[0]
    edits = []
    for chunk in out.alignments[0]:
        if chunk.type == "equal":
            continue
        edits.append(
            {
                "type": chunk.type,
                "ref": " ".join(ref_w[chunk.ref_start_idx : chunk.ref_end_idx]),
                "hyp": " ".join(hyp_w[chunk.hyp_start_idx : chunk.hyp_end_idx]),
            }
        )
    return edits


def levenshtein_distance(ref: Sequence[str], hyp: Sequence[str]) -> int:
    if not ref:
        return len(hyp)
    prev = list(range(len(hyp) + 1))
    for i, r_item in enumerate(ref, 1):
        cur = [i]
        for j, h_item in enumerate(hyp, 1):
            cur.append(
                min(
                    prev[j] + 1,
                    cur[j - 1] + 1,
                    prev[j - 1] + (0 if r_item == h_item else 1),
                )
            )
        prev = cur
    return prev[-1]


def score_and_diff(lang: str, ref: str, hyp: str, include_edits: bool) -> Dict[str, Any]:
    if jiwer is None:
        raise RuntimeError("WER scoring requires jiwer")

    if lang == "zh":
        ref_chars = list(normalize_zh_chars(ref))
        hyp_chars = list(normalize_zh_chars(hyp))
        denom = max(1, len(ref_chars))
        cer = levenshtein_distance(ref_chars, hyp_chars) / denom
        out = jiwer.process_words(zh_pinyin_tone3(ref), zh_pinyin_tone3(hyp))
        return {
            "wer": out.wer,
            "cer": cer,
            "zh_pinyin_tone3_wer": out.wer,
            "edits": alignment_edits(out) if include_edits else [],
        }

    if lang == "en":
        out = jiwer.process_words(normalize_en(ref), normalize_en(hyp))
        return {
            "wer": out.wer,
            "cer": None,
            "zh_pinyin_tone3_wer": None,
            "edits": alignment_edits(out) if include_edits else [],
        }

    raise RuntimeError(f"Unsupported language for scoring: {lang!r}")


def audio_to_data_url(path: Path) -> str:
    suffix = path.suffix.lower()
    mime = {
        ".flac": "audio/flac",
        ".wav": "audio/wav",
        ".mp3": "audio/mpeg",
        ".m4a": "audio/mp4",
    }.get(suffix, "application/octet-stream")
    with path.open("rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:{mime};base64,{b64}"


def parse_hyp_text(raw: str) -> str:
    if qwen_parse_asr_output is not None:
        try:
            parsed = qwen_parse_asr_output(raw)
            if isinstance(parsed, tuple) and len(parsed) >= 2:
                return str(parsed[1])
        except Exception as exc:  # pragma: no cover - fallback preserves raw.
            logger.warning("qwen_asr.parse_asr_output failed; using raw content: %s", exc)
    return str(raw).strip()


def call_asr(
    audio_path: Path,
    start_port: int,
    ports: Sequence[int],
    endpoint_template: str,
    timeout: int,
    max_retries: int,
) -> str:
    if requests is None:
        raise RuntimeError("ASR calls require requests")
    payload = {
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "audio_url",
                        "audio_url": {"url": audio_to_data_url(audio_path)},
                    }
                ],
            }
        ]
    }
    start_idx = ports.index(start_port)
    last_err: Optional[BaseException] = None
    attempts = max(1, max_retries)
    for attempt in range(attempts):
        port = ports[(start_idx + attempt) % len(ports)]
        try:
            response = requests.post(
                endpoint_template.format(port=port),
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=timeout,
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]
        except requests.RequestException as exc:
            last_err = exc
            if attempt < attempts - 1:
                next_port = ports[(start_idx + attempt + 1) % len(ports)]
                logger.warning(
                    "ASR retry %d/%d port=%d -> %d: %s",
                    attempt + 1,
                    attempts,
                    port,
                    next_port,
                    exc,
                )
                time.sleep(2**attempt)
    raise RuntimeError(f"ASR request failed after {attempts} attempts: {last_err}")


def record_from_manifest(raw: Dict[str, Any], args: argparse.Namespace) -> Dict[str, Any]:
    missing = [
        field
        for field in (args.id_field, args.audio_field, args.ref_text_field, args.lang_field)
        if field not in raw
    ]
    if missing:
        raise ValueError(f"manifest record missing required fields: {missing}")
    wav = str(raw[args.audio_field])
    lang = normalize_lang(raw.get(args.lang_field))
    audio_path = resolve_audio_path(wav, Path(args.audio_root))
    return {
        "id": str(raw[args.id_field]),
        "wav": wav,
        "audio_path": str(audio_path),
        "language": lang,
        "source_language": raw.get(args.lang_field),
        "ref_text": str(raw.get(args.ref_text_field) or ""),
        "duration": raw.get(args.duration_field),
        "manifest_record": raw,
    }


def record_from_legacy_meta(raw: Dict[str, Any]) -> Dict[str, Any]:
    missing = [field for field in ("task_id", "output_audio", "edited_text", "lang") if field not in raw]
    if missing:
        raise ValueError(f"legacy metafile record missing required fields: {missing}")
    lang = normalize_lang(raw["lang"])
    return {
        "id": str(raw["task_id"]),
        "wav": str(raw["output_audio"]),
        "audio_path": str(Path(raw["output_audio"])),
        "language": lang,
        "source_language": raw.get("lang"),
        "ref_text": str(raw.get("edited_text") or ""),
        "duration": raw.get("duration"),
        "manifest_record": raw,
    }


def iter_records(args: argparse.Namespace) -> Iterator[Dict[str, Any]]:
    count = 0
    if args.path:
        meta_in = Path(args.path) / "metafile.jsonl"
        for raw in iter_jsonl(meta_in):
            yield record_from_legacy_meta(raw)
            count += 1
            if args.limit is not None and count >= args.limit:
                return

    for manifest in args.manifest or []:
        for raw in iter_jsonl(Path(manifest)):
            yield record_from_manifest(raw, args)
            count += 1
            if args.limit is not None and count >= args.limit:
                return


def load_records(args: argparse.Namespace) -> List[Dict[str, Any]]:
    return list(iter_records(args))


def read_done_ids(output: Optional[Path]) -> set:
    done = set()
    if output is None or not output.exists():
        return done
    for rec in iter_jsonl(output):
        rec_id = rec.get("id") or rec.get("task_id")
        if rec_id is not None:
            done.add(str(rec_id))
    return done


def process_one(
    meta: Dict[str, Any],
    port: int,
    ports: Sequence[int],
    args: argparse.Namespace,
) -> Dict[str, Any]:
    base = {
        "id": meta["id"],
        "audio_path": meta["audio_path"],
        "wav": meta["wav"],
        "language": meta["language"],
        "source_language": meta["source_language"],
        "ref_text": meta["ref_text"],
        "duration": meta.get("duration"),
        "hyp_text": None,
        "raw_asr_output": None,
        "wer": None,
        "cer": None,
        "zh_pinyin_tone3_wer": None,
        "edits": [],
        "error": None,
    }

    try:
        if meta["language"] not in {"zh", "en"}:
            raise RuntimeError(f"unsupported language: {meta['source_language']!r}")
        audio_path = Path(meta["audio_path"])
        if not audio_path.exists():
            raise FileNotFoundError(str(audio_path))
        raw = call_asr(
            audio_path=audio_path,
            start_port=port,
            ports=ports,
            endpoint_template=args.endpoint_template,
            timeout=args.timeout,
            max_retries=args.max_retries,
        )
        hyp_text = parse_hyp_text(raw)
        scores = score_and_diff(meta["language"], meta["ref_text"], hyp_text, args.include_edits)
        base.update(scores)
        base["hyp_text"] = hyp_text
        base["raw_asr_output"] = raw
    except Exception as exc:
        base["error"] = str(exc)
    return base


def dependency_status(records: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    has_zh = any(rec.get("language") == "zh" for rec in records)
    return {
        "requests": requests is not None,
        "jiwer": jiwer is not None,
        "pypinyin": lazy_pinyin is not None and Style is not None,
        "qwen_asr_parse": qwen_parse_asr_output is not None,
        "opencc": OpenCC is not None,
        "zhconv": zhconv is not None,
        "zh_simplifier_available": OpenCC is not None or zhconv is not None,
        "zh_records_present": has_zh,
    }


def dry_run(records: Sequence[Dict[str, Any]], args: argparse.Namespace) -> int:
    logger.info("dry-run: loaded %d records", len(records))
    logger.info("dry-run: ports=%s", parse_ports(args.ports))
    status = dependency_status(records)
    logger.info("dry-run dependency status: %s", json.dumps(status, ensure_ascii=False))
    for rec in records[: min(5, len(records))]:
        audio_path = Path(rec["audio_path"])
        logger.info(
            "sample id=%s lang=%s wav=%s audio_exists=%s duration=%s",
            rec["id"],
            rec["language"],
            rec["wav"],
            audio_path.exists(),
            rec.get("duration"),
        )
    blockers = []
    if not status["requests"]:
        blockers.append("requests is unavailable")
    if not status["jiwer"]:
        blockers.append("jiwer is unavailable")
    if status["zh_records_present"] and not status["pypinyin"]:
        blockers.append("pypinyin is unavailable for zh pinyin WER")
    if status["zh_records_present"] and not status["zh_simplifier_available"]:
        blockers.append("opencc/zhconv unavailable for zh CER simplification")
    if status["zh_records_present"] and status["zh_simplifier_available"]:
        try:
            simplify_zh("繁體中文")
        except Exception as exc:
            blockers.append(f"zh simplifier failed to initialize: {exc}")
    if blockers:
        logger.error("dry-run blockers: %s", "; ".join(blockers))
        return 2
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description=(
            "Run Qwen3-ASR verification on Jellycat manifests or a legacy "
            "metafile.jsonl directory. Outputs sidecar JSONL and never edits "
            "the source manifest."
        )
    )
    ap.add_argument("--path", help="Legacy directory containing metafile.jsonl")
    ap.add_argument("--manifest", action="append", help="Input .jsonl or .jsonl.gz manifest; can repeat")
    ap.add_argument("--output", help="Sidecar JSONL output path")
    ap.add_argument("--failed-output", help="Optional JSONL path for failed records")
    ap.add_argument("--audio_root", "--audio-root", default=DEFAULT_AUDIO_ROOT)
    ap.add_argument("--id-field", default="id")
    ap.add_argument("--audio-field", default="wav")
    ap.add_argument("--ref-text-field", default="text")
    ap.add_argument("--lang-field", default="language")
    ap.add_argument("--duration-field", default="duration")
    ap.add_argument("--ports", default=DEFAULT_PORTS)
    ap.add_argument("--endpoint-template", default="http://localhost:{port}/v1/chat/completions")
    ap.add_argument("--workers-per-port", type=int, default=1)
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--max-retries", type=int, default=3)
    ap.add_argument(
        "--max-inflight",
        type=int,
        default=0,
        help="Maximum queued futures; default is workers * 4.",
    )
    ap.add_argument("--limit", type=int)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-edits", dest="include_edits", action="store_false")
    ap.set_defaults(include_edits=True)
    return ap


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()

    if not args.path and not args.manifest:
        parser.error("Provide --manifest and/or legacy --path")

    output = Path(args.output) if args.output else None
    if output is None and args.path:
        output = Path(args.path) / "verify_meta.jsonl"
    if output is None and not args.dry_run:
        parser.error("--output is required for manifest mode unless --dry-run is set")

    failed_output = Path(args.failed_output) if args.failed_output else None
    records = load_records(args) if args.dry_run else None
    if args.dry_run:
        return dry_run(records, args)

    preview_args = argparse.Namespace(**vars(args))
    preview_args.limit = 128 if args.limit is None else min(args.limit, 128)
    preview_records = load_records(preview_args)
    if not preview_records:
        logger.info("No input records; exiting")
        return 0
    preview_status = dependency_status(preview_records)
    preflight_blockers = []
    if not preview_status["requests"]:
        preflight_blockers.append("requests is unavailable")
    if not preview_status["jiwer"]:
        preflight_blockers.append("jiwer is unavailable")
    if preview_status["zh_records_present"] and not preview_status["pypinyin"]:
        preflight_blockers.append("pypinyin is unavailable for zh pinyin WER")
    if preview_status["zh_records_present"] and not preview_status["zh_simplifier_available"]:
        preflight_blockers.append("opencc/zhconv unavailable for zh CER simplification")
    if preview_status["zh_records_present"] and preview_status["zh_simplifier_available"]:
        try:
            simplify_zh("繁體中文")
        except Exception as exc:
            preflight_blockers.append(f"zh simplifier failed to initialize: {exc}")
    if preflight_blockers:
        logger.error("preflight blockers: %s", "; ".join(preflight_blockers))
        return 2

    done = read_done_ids(output)
    ports = parse_ports(args.ports)
    total_workers = max(1, args.workers_per_port) * len(ports)
    max_inflight = args.max_inflight if args.max_inflight > 0 else total_workers * 4
    logger.info(
        "workers=%d ports=%s max_inflight=%d output=%s resume_done=%d",
        total_workers,
        ports,
        max_inflight,
        output,
        len(done),
    )

    assert output is not None
    output.parent.mkdir(parents=True, exist_ok=True)
    if failed_output is not None:
        failed_output.parent.mkdir(parents=True, exist_ok=True)

    port_iter = cycle(ports)
    write_lock = threading.Lock()
    pbar = tqdm(desc="ASR verify", unit="utt") if tqdm is not None else None
    failures = 0
    submitted = 0
    completed = 0
    skipped = 0

    with output.open("a", encoding="utf-8") as fout:
        ffail = failed_output.open("a", encoding="utf-8") if failed_output else None
        try:
            with ThreadPoolExecutor(max_workers=total_workers) as pool:
                futures = {}
                records_iter = iter_records(args)
                exhausted = False

                while futures or not exhausted:
                    while not exhausted and len(futures) < max_inflight:
                        try:
                            rec_in = next(records_iter)
                        except StopIteration:
                            exhausted = True
                            break
                        if rec_in["id"] in done:
                            skipped += 1
                            continue
                        fut = pool.submit(process_one, rec_in, next(port_iter), ports, args)
                        futures[fut] = rec_in["id"]
                        submitted += 1

                    if not futures:
                        continue

                    ready, _ = wait(futures, return_when=FIRST_COMPLETED)
                    for fut in ready:
                        futures.pop(fut, None)
                        rec_out = fut.result()
                        completed += 1
                        with write_lock:
                            fout.write(json.dumps(rec_out, ensure_ascii=False) + "\n")
                            fout.flush()
                            if rec_out.get("error") and ffail is not None:
                                ffail.write(json.dumps(rec_out, ensure_ascii=False) + "\n")
                                ffail.flush()
                        if rec_out.get("error"):
                            failures += 1
                        if pbar is not None:
                            pbar.update(1)
        finally:
            if pbar is not None:
                pbar.close()
            if ffail is not None:
                ffail.close()

    logger.info("submitted=%d completed=%d skipped=%d", submitted, completed, skipped)
    if failures:
        logger.warning("Completed with %d failed records", failures)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
