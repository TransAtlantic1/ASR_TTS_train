#!/usr/bin/env python3

from __future__ import annotations

import argparse
import copy
import hashlib
import logging
import os
import sys
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, List, Sequence, Tuple

from bench_registry import BENCH2_ROOT, RESULTS_ROOT, DatasetSpec, resolve_dataset_ids, specs_for


ICEFALL_ROOT = Path(__file__).resolve().parents[4]
if str(ICEFALL_ROOT) not in sys.path:
    sys.path.insert(0, str(ICEFALL_ROOT))


def get_parser():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("--language", type=str, required=True, choices=["zh", "en"])
    parser.add_argument("--mode", type=str, default="once", choices=["once", "watch"])
    parser.add_argument("--bench-root", type=Path, default=BENCH2_ROOT)
    parser.add_argument("--results-root", type=Path, default=RESULTS_ROOT)
    parser.add_argument("--test-sets", type=str, default="")
    parser.add_argument("--test-set-preset", type=str, default="")
    parser.add_argument("--ref-modes", type=str, default="raw,normalized")
    parser.add_argument("--exp-dir", type=str, required=True)
    parser.add_argument("--artifact-root", type=str, default="")
    parser.add_argument("--manifest-dir", type=str, default="")
    parser.add_argument("--lang-dir", type=str, default="")
    parser.add_argument("--bpe-model", type=str, default="")
    parser.add_argument("--avg", type=int, default=3)
    parser.add_argument("--beam-size", type=int, default=4)
    parser.add_argument("--decoding-methods", type=str, default="greedy_search,modified_beam_search")
    parser.add_argument("--decode-every-n", type=int, default=5000)
    parser.add_argument("--poll-seconds", type=int, default=120)
    parser.add_argument("--decode-max-duration", type=float, default=1000.0)
    parser.add_argument("--decode-num-workers", type=int, default=0)
    parser.add_argument("--decode-cuda-visible-devices", type=str, default="")
    parser.add_argument("--use-averaged-model", type=str, default="true")
    parser.add_argument("--start-iter", type=int, default=0)
    parser.add_argument("--iter", type=int, default=0)
    parser.add_argument("--epoch", type=int, default=0)
    parser.add_argument("--state-dir", type=str, default="")
    parser.add_argument("--log-path", type=str, default="")
    parser.add_argument("--train-done-marker", type=str, default="")
    parser.add_argument("--once", type=str, default="false")
    parser.add_argument("--dry-run", type=str, default="false")
    parser.add_argument("--auto-resolve-run-dir", type=str, default="true")
    parser.add_argument("--skip-unavailable", type=str, default="false")
    return parser


def str2bool(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    normalized = value.strip().lower()
    if normalized in ("1", "true", "t", "yes", "y"):
        return True
    if normalized in ("0", "false", "f", "no", "n"):
        return False
    raise ValueError(f"Unsupported boolean value: {value}")


def default_state_dir(language: str, exp_dir: str) -> Path:
    digest = hashlib.sha1(exp_dir.encode("utf-8")).hexdigest()[:12]
    return Path("/tmp/icefall-auto-eval") / f"{language}-{digest}"


def trim_spaces(value: str) -> str:
    return "".join(value.split())


def parse_csv(value: str) -> List[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def resolve_watch_dir(base_dir: str, auto_resolve_run_dir: bool) -> Path:
    base_path = Path(base_dir)
    if list(base_path.glob("checkpoint-*.pt")):
        return base_path
    if base_path.name.startswith("run-"):
        return base_path
    if auto_resolve_run_dir and base_path.is_dir():
        candidates = sorted(path for path in base_path.iterdir() if path.is_dir() and path.name.startswith("run-"))
        if candidates:
            return candidates[-1]
    return base_path


def checkpoint_iter_from_path(path: Path) -> int:
    name = path.name
    if not name.startswith("checkpoint-") or not name.endswith(".pt"):
        raise ValueError(f"Unsupported checkpoint name: {path}")
    return int(name[len("checkpoint-") : -len(".pt")])


def decode_suffix(params) -> str:
    if params.iter > 0:
        suffix = f"iter-{params.iter}-avg-{params.avg}"
    else:
        suffix = f"epoch-{params.epoch}-avg-{params.avg}"

    if params.causal:
        suffix += f"-chunk-{params.chunk_size}"
        suffix += f"-left-context-{params.left_context_frames}"

    if "fast_beam_search" in params.decoding_method:
        suffix += f"-beam-{params.beam}"
        suffix += f"-max-contexts-{params.max_contexts}"
        suffix += f"-max-states-{params.max_states}"
        if "nbest" in params.decoding_method:
            suffix += f"-nbest-scale-{params.nbest_scale}"
            suffix += f"-num-paths-{params.num_paths}"
            if "LG" in params.decoding_method:
                suffix += f"-ngram-lm-scale-{params.ngram_lm_scale}"
    elif "beam_search" in params.decoding_method:
        suffix += f"-{params.decoding_method}-beam-size-{params.beam_size}"
        if params.decoding_method in ("modified_beam_search", "modified_beam_search_LODR"):
            if params.has_contexts:
                suffix += f"-context-score-{params.context_score}"
    else:
        suffix += f"-context-{params.context_size}"
        suffix += f"-max-sym-per-frame-{params.max_sym_per_frame}"

    if getattr(params, "use_shallow_fusion", False):
        suffix += f"-{params.lm_type}-lm-scale-{params.lm_scale}"
        if "LODR" in params.decoding_method:
            suffix += f"-LODR-{params.tokens_ngram}gram-scale-{params.ngram_lm_scale}"

    if params.use_averaged_model:
        suffix += "-use-averaged-model"
    return suffix


def build_base_args(parsed) -> argparse.Namespace:
    return argparse.Namespace(
        language=parsed.language,
        artifact_root=parsed.artifact_root,
        manifest_dir=parsed.manifest_dir or None,
        lang_dir=parsed.lang_dir or None,
        bpe_model=parsed.bpe_model or None,
        exp_dir=parsed.exp_dir,
    )


def clone_with_exp_dir(parsed, exp_dir: Path):
    cloned = SimpleNamespace(**vars(parsed))
    cloned.exp_dir = str(exp_dir)
    return cloned


def build_data_args(modules, params, parsed) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    modules.asr_datamodule.EmiliaAsrDataModule.add_arguments(parser)
    data_args = parser.parse_args([])
    data_args.language = parsed.language
    data_args.return_cuts = True
    data_args.max_duration = parsed.decode_max_duration
    data_args.num_workers = parsed.decode_num_workers
    data_args.transcript_source = "text"
    data_args.manifest_dir = params.manifest_dir
    return data_args


def create_model_bundle(parsed):
    from recipe_loader import create_tokenizer, load_recipe_modules

    modules = load_recipe_modules(parsed.language)
    train_parser = modules.train.get_parser()
    decode_parser = modules.decode.get_parser()
    args = train_parser.parse_args([])
    decode_args = decode_parser.parse_args([])
    args.language = parsed.language
    args.artifact_root = parsed.artifact_root
    args.manifest_dir = parsed.manifest_dir or None
    args.lang_dir = parsed.lang_dir or None
    args.bpe_model = parsed.bpe_model or None
    args.exp_dir = parsed.exp_dir
    args.auto_exp_subdir = False
    args = modules.train.normalize_emilia_args(args)
    params = modules.train.get_params()
    params.update(vars(decode_args))
    params.update(vars(args))
    params.iter = 0
    params.epoch = 0
    params.use_averaged_model = str2bool(parsed.use_averaged_model)
    tokenizer = create_tokenizer(modules, parsed.language, params)
    model = modules.train.get_model(params)
    return modules, params, tokenizer, model


def load_model_for_checkpoint(modules, params, model, device) -> None:
    if not params.use_averaged_model:
        if params.iter > 0:
            filenames = modules.decode.find_checkpoints(params.exp_dir, iteration=-params.iter)[: params.avg]
            if len(filenames) < params.avg:
                raise ValueError(f"Not enough checkpoints for iter={params.iter}, avg={params.avg}")
            model.to(device)
            model.load_state_dict(modules.decode.average_checkpoints(filenames, device=device))
        elif params.avg == 1:
            modules.decode.load_checkpoint(f"{params.exp_dir}/epoch-{params.epoch}.pt", model)
        else:
            start = params.epoch - params.avg + 1
            filenames = [f"{params.exp_dir}/epoch-{i}.pt" for i in range(start, params.epoch + 1) if i >= 1]
            model.to(device)
            model.load_state_dict(modules.decode.average_checkpoints(filenames, device=device))
    else:
        if params.iter > 0:
            filenames = modules.decode.find_checkpoints(params.exp_dir, iteration=-params.iter)[: params.avg + 1]
            if len(filenames) < params.avg + 1:
                raise ValueError(
                    f"Not enough checkpoints for iter={params.iter}, avg={params.avg}, use_averaged_model=true"
                )
            filename_start = filenames[-1]
            filename_end = filenames[0]
            model.to(device)
            model.load_state_dict(
                modules.decode.average_checkpoints_with_averaged_model(
                    filename_start=filename_start,
                    filename_end=filename_end,
                    device=device,
                )
            )
        else:
            start = params.epoch - params.avg
            if start < 1:
                raise ValueError(f"Invalid epoch/avg combination: epoch={params.epoch}, avg={params.avg}")
            model.to(device)
            model.load_state_dict(
                modules.decode.average_checkpoints_with_averaged_model(
                    filename_start=f"{params.exp_dir}/epoch-{start}.pt",
                    filename_end=f"{params.exp_dir}/epoch-{params.epoch}.pt",
                    device=device,
                )
            )
    model.to(device)
    model.eval()


def build_method_resources(modules, params, model, tokenizer, device):
    from icefall import ContextGraph, LmScorer, NgramLm

    if getattr(params, "use_shallow_fusion", False) or params.decoding_method in (
        "modified_beam_search_lm_rescore",
        "modified_beam_search_lm_rescore_LODR",
        "modified_beam_search_lm_shallow_fusion",
        "modified_beam_search_LODR",
    ):
        lm = LmScorer(
            lm_type=params.lm_type,
            params=params,
            device=device,
            lm_scale=params.lm_scale,
        )
        lm.to(device)
        lm.eval()
    else:
        lm = None

    if params.decoding_method == "modified_beam_search_lm_rescore_LODR":
        import kenlm

        ngram_lm = kenlm.Model(str(params.lang_dir / f"{params.tokens_ngram}gram.arpa"))
        ngram_lm_scale = None
    elif params.decoding_method == "modified_beam_search_LODR":
        ngram_lm = NgramLm(
            str(params.lang_dir / f"{params.tokens_ngram}gram.fst.txt"),
            backoff_id=params.backoff_id,
            is_binary=False,
        )
        ngram_lm_scale = params.ngram_lm_scale
    else:
        ngram_lm = None
        ngram_lm_scale = None

    if "fast_beam_search" in params.decoding_method:
        import k2

        if params.decoding_method == "fast_beam_search_nbest_LG":
            lexicon = modules.decode.Lexicon(params.lang_dir)
            word_table = lexicon.word_table
            decoding_graph = k2.Fsa.from_dict(
                torch.load(params.lang_dir / "LG.pt", map_location=device, weights_only=False)
            )
            decoding_graph.scores *= params.ngram_lm_scale
        else:
            word_table = None
            decoding_graph = k2.trivial_graph(params.vocab_size - 1, device=device)
    else:
        decoding_graph = None
        word_table = None

    if "modified_beam_search" in params.decoding_method and os.path.exists(params.context_file):
        contexts = []
        normalizer = getattr(modules.decode, "normalize_text", None)
        if normalizer is None:
            normalizer = lambda text, language: text
        with open(params.context_file, "r", encoding="utf-8") as f:
            for line in f:
                context = normalizer(line.strip(), params.language)
                if context:
                    contexts.append(context)
        if contexts:
            context_graph = ContextGraph(params.context_score)
            if params.language == "zh":
                encoded = modules.train.encode_texts(tokenizer, contexts, params.language)
            else:
                encoded = tokenizer.encode(modules.train.texts_to_sp_inputs(contexts, params.language))
            context_graph.build(encoded)
        else:
            context_graph = None
    else:
        context_graph = None

    return {
        "LM": lm,
        "ngram_lm": ngram_lm,
        "ngram_lm_scale": ngram_lm_scale,
        "word_table": word_table,
        "decoding_graph": decoding_graph,
        "context_graph": context_graph,
    }


def decode_one_batch(modules, language, params, model, tokenizer, batch, resources):
    kwargs = dict(
        params=params,
        model=model,
        batch=batch,
        word_table=resources["word_table"],
        decoding_graph=resources["decoding_graph"],
        context_graph=resources["context_graph"],
        LM=resources["LM"],
        ngram_lm=resources["ngram_lm"],
        ngram_lm_scale=resources["ngram_lm_scale"],
    )
    if language == "zh":
        kwargs["tokenizer"] = tokenizer
    else:
        kwargs["sp"] = tokenizer
    return modules.decode.decode_one_batch(**kwargs)


def raw_and_normalized_text(cut) -> Tuple[str, str]:
    raw_texts = []
    normalized_texts = []
    for supervision in cut.supervisions:
        custom = getattr(supervision, "custom", None) or {}
        raw_texts.append(str(custom.get("raw_text") or supervision.text or "").strip())
        normalized_texts.append(str(supervision.text or "").strip())
    return " ".join(text for text in raw_texts if text), " ".join(text for text in normalized_texts if text)


def sanitize_eval_cuts(cuts):
    from lhotse.utils import compute_num_frames, fastcopy

    min_decode_num_frames = 9
    dropped = 0
    repaired = 0

    def _transform(cut):
        nonlocal dropped, repaired

        if cut.duration <= 0:
            dropped += 1
            return cut

        features = getattr(cut, "features", None)
        if features is not None:
            frame_shift = getattr(cut, "frame_shift", None) or getattr(features, "frame_shift", None)
            sampling_rate = getattr(cut, "sampling_rate", None) or getattr(features, "sampling_rate", None)
            if frame_shift and sampling_rate:
                expected_num_frames = compute_num_frames(
                    duration=cut.duration,
                    frame_shift=frame_shift,
                    sampling_rate=sampling_rate,
                )
            else:
                expected_num_frames = getattr(features, "num_frames", None)

            if expected_num_frames is None or expected_num_frames <= 0:
                dropped += 1
                return cut

            if expected_num_frames < min_decode_num_frames:
                dropped += 1
                return cut

            if getattr(features, "num_frames", None) != expected_num_frames:
                repaired += 1
                return fastcopy(cut, features=fastcopy(features, num_frames=expected_num_frames))
            return cut

        if getattr(cut, "num_frames", None) is not None and cut.num_frames < min_decode_num_frames:
            dropped += 1
            return cut

        return cut

    sanitized = cuts.map(_transform)
    sanitized = sanitized.filter(
        lambda cut: cut.duration > 0
        and (
            getattr(cut, "features", None) is None
            or getattr(cut.features, "num_frames", 0) >= min_decode_num_frames
        )
        and (
            getattr(cut, "num_frames", None) is None
            or cut.num_frames >= min_decode_num_frames
        )
    )
    return sanitized, repaired, dropped


def decode_dataset_records(
    modules,
    parsed,
    params,
    model,
    tokenizer,
    data_args,
    spec: DatasetSpec,
    resources,
) -> Dict[str, List[ScoreRecord]]:
    from lhotse import CutSet
    from recipe_loader import hyp_to_text
    from scoring import ScoreRecord

    cut_path = spec.prepared_cut_path(parsed.bench_root)
    cuts = CutSet.from_file(cut_path)
    cuts, repaired_cuts, dropped_cuts = sanitize_eval_cuts(cuts)
    if repaired_cuts or dropped_cuts:
        logging.warning(
            "Eval cut sanitization for %s repaired=%s dropped=%s",
            spec.dataset_id,
            repaired_cuts,
            dropped_cuts,
        )
    datamodule = modules.asr_datamodule.EmiliaAsrDataModule(data_args)
    dl = datamodule.test_dataloaders(cuts)
    records = defaultdict(list)
    for batch in dl:
        hyps_dict = decode_one_batch(modules, parsed.language, params, model, tokenizer, batch, resources)
        cut_items = batch["supervisions"]["cut"]
        for decode_key, hyps in hyps_dict.items():
            for cut, hyp in zip(cut_items, hyps):
                raw_text, normalized_text = raw_and_normalized_text(cut)
                records[decode_key].append(
                    ScoreRecord(
                        cut_id=cut.id,
                        dataset_id=spec.dataset_id,
                        ref_raw_text=raw_text,
                        ref_normalized_text=normalized_text,
                        hyp_text=hyp_to_text(parsed.language, hyp),
                    )
                )
    return records


def evaluate_checkpoint(parsed, dataset_specs: Sequence[DatasetSpec], iter_value: int = 0, epoch_value: int = 0) -> Path:
    import torch
    from scoring import parse_csv, score_records, write_jsonl, write_transcripts

    modules, base_params, tokenizer, model = create_model_bundle(parsed)
    device = torch.device("cpu")
    if torch.cuda.is_available():
        device = torch.device("cuda", 0)

    base_params.iter = iter_value
    base_params.epoch = epoch_value if iter_value <= 0 else base_params.epoch
    base_params.avg = parsed.avg
    base_params.beam_size = parsed.beam_size
    base_params.max_duration = parsed.decode_max_duration
    base_params.num_workers = parsed.decode_num_workers
    load_model_for_checkpoint(modules, base_params, model, device)
    data_args = build_data_args(modules, base_params, parsed)
    ref_modes = parse_csv(parsed.ref_modes)
    metrics_rows = []
    summary_dir = parsed.results_root / "_summary"
    summary_dir.mkdir(parents=True, exist_ok=True)

    for method in parse_csv(parsed.decoding_methods):
        params = copy.deepcopy(base_params)
        params.decoding_method = method
        params.has_contexts = os.path.exists(params.context_file)
        params.suffix = decode_suffix(params)
        resources = build_method_resources(modules, params, model, tokenizer, device)

        for spec in dataset_specs:
            params.res_dir = parsed.results_root / spec.dataset_id / params.suffix / method
            params.res_dir.mkdir(parents=True, exist_ok=True)
            records_by_key = decode_dataset_records(
                modules=modules,
                parsed=parsed,
                params=params,
                model=model,
                tokenizer=tokenizer,
                data_args=data_args,
                spec=spec,
                resources=resources,
            )
            for decode_key, records in records_by_key.items():
                write_transcripts(records, spec.dataset_id, decode_key, params.res_dir, params.suffix)
                write_jsonl(
                    params.res_dir / f"recogs-{spec.dataset_id}-{decode_key}-{params.suffix}.jsonl",
                    [
                        {
                            "cut_id": record.cut_id,
                            "dataset_id": record.dataset_id,
                            "ref_raw_text": record.ref_raw_text,
                            "ref_normalized_text": record.ref_normalized_text,
                            "hyp_text": record.hyp_text,
                        }
                        for record in records
                    ],
                )
                metric_values = score_records(
                    records=records,
                    language=parsed.language,
                    dataset_id=spec.dataset_id,
                    decode_key=decode_key,
                    res_dir=params.res_dir,
                    suffix=params.suffix,
                    ref_modes=ref_modes,
                    use_speechio_hook=spec.speechio_official_norm,
                )
                for metric_name, value in sorted(metric_values.items()):
                    metrics_rows.append(
                        {
                            "dataset_id": spec.dataset_id,
                            "method": method,
                            "decode_key": decode_key,
                            "metric": metric_name,
                            "value": value,
                            "suffix": params.suffix,
                        }
                    )

    metrics_path = summary_dir / (
        f"iter-{iter_value}.metrics.jsonl" if iter_value > 0 else f"epoch-{epoch_value}.metrics.jsonl"
    )
    write_jsonl(metrics_path, metrics_rows)
    tsv_path = metrics_path.with_suffix(".tsv")
    tsv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(tsv_path, "w", encoding="utf-8") as f:
        f.write("dataset_id\tmethod\tdecode_key\tmetric\tvalue\tsuffix\n")
        for row in metrics_rows:
            f.write(
                f"{row['dataset_id']}\t{row['method']}\t{row['decode_key']}\t{row['metric']}\t{row['value']}\t{row['suffix']}\n"
            )
    return metrics_path


def eligible_iters(exp_dir: Path, avg: int, decode_every_n: int, start_iter: int, use_averaged_model: bool) -> List[int]:
    checkpoint_paths = sorted(exp_dir.glob("checkpoint-*.pt"), key=lambda path: checkpoint_iter_from_path(path))
    required = avg + 1 if use_averaged_model else avg
    output = []
    for index, path in enumerate(checkpoint_paths):
        iter_value = checkpoint_iter_from_path(path)
        if iter_value < start_iter:
            continue
        if decode_every_n > 0 and iter_value % decode_every_n != 0:
            continue
        if index + 1 < required:
            continue
        output.append(iter_value)
    return output


def iter_already_done(decoded_iters_file: Path, iter_value: int) -> bool:
    if not decoded_iters_file.is_file():
        return False
    return any(line.strip() == str(iter_value) for line in decoded_iters_file.read_text().splitlines())


def watch(parsed, dataset_specs: Sequence[DatasetSpec]) -> None:
    state_dir = Path(parsed.state_dir) if parsed.state_dir else default_state_dir(parsed.language, parsed.exp_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    decoded_iters_file = state_dir / "evaluated_iters.txt"
    once = str2bool(parsed.once)
    auto_resolve_run_dir = str2bool(parsed.auto_resolve_run_dir)
    use_averaged_model = str2bool(parsed.use_averaged_model)

    while True:
        resolved_exp_dir = resolve_watch_dir(parsed.exp_dir, auto_resolve_run_dir)
        pending = [
            iter_value
            for iter_value in eligible_iters(
                resolved_exp_dir,
                parsed.avg,
                parsed.decode_every_n,
                parsed.start_iter,
                use_averaged_model,
            )
            if not iter_already_done(decoded_iters_file, iter_value)
        ]

        for iter_value in pending:
            if str2bool(parsed.dry_run):
                logging.info("Dry run: would evaluate iter=%s", iter_value)
                continue
            evaluate_checkpoint(
                clone_with_exp_dir(parsed, resolved_exp_dir),
                dataset_specs,
                iter_value=iter_value,
            )
            with open(decoded_iters_file, "a", encoding="utf-8") as f:
                f.write(f"{iter_value}\n")

        if once:
            return

        if parsed.train_done_marker and Path(parsed.train_done_marker).exists() and not pending:
            return

        import time

        time.sleep(parsed.poll_seconds)


def main():
    parsed = get_parser().parse_args()
    if parsed.decode_cuda_visible_devices:
        os.environ["CUDA_VISIBLE_DEVICES"] = parsed.decode_cuda_visible_devices

    dataset_specs = specs_for(
        parsed.language,
        resolve_dataset_ids(
            parsed.language,
            dataset_ids=parse_csv(parsed.test_sets),
            preset_names=parse_csv(parsed.test_set_preset),
        ),
    )
    if str2bool(parsed.skip_unavailable):
        dataset_specs = [
            spec
            for spec in dataset_specs
            if spec.prepared_cut_path(parsed.bench_root).is_file()
        ]
    if not dataset_specs:
        raise RuntimeError("No prepared datasets were found for the requested evaluation set.")

    if parsed.mode == "watch":
        watch(parsed, dataset_specs)
        return

    if parsed.iter > 0:
        evaluate_checkpoint(parsed, dataset_specs, iter_value=parsed.iter)
        return
    if parsed.epoch > 0:
        evaluate_checkpoint(parsed, dataset_specs, epoch_value=parsed.epoch)
        return

    resolved_exp_dir = resolve_watch_dir(parsed.exp_dir, str2bool(parsed.auto_resolve_run_dir))
    pending = eligible_iters(
        resolved_exp_dir,
        parsed.avg,
        parsed.decode_every_n,
        parsed.start_iter,
        str2bool(parsed.use_averaged_model),
    )
    if not pending:
        raise RuntimeError(f"No eligible checkpoints found under {resolved_exp_dir}")
    evaluate_checkpoint(
        clone_with_exp_dir(parsed, resolved_exp_dir),
        dataset_specs,
        iter_value=pending[-1],
    )


if __name__ == "__main__":
    logging.basicConfig(
        format="%(asctime)s %(levelname)s [%(filename)s:%(lineno)d] %(message)s",
        level=logging.INFO,
    )
    main()
