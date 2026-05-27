#!/usr/bin/env python3

from __future__ import annotations

import argparse
import importlib
import importlib.util
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

import sentencepiece as spm

from bench_registry import ZIPFORMER_24K_MULTILANG_ROOT


@dataclass
class RecipeModules:
    recipe_root: Path
    zipformer_dir: Path
    local_dir: Path
    decode: Any
    train: Any
    asr_datamodule: Any


def recipe_root_for_language(language: str) -> Path:
    language = language.lower()
    if language == "zh":
        return ZIPFORMER_24K_MULTILANG_ROOT / "zipformer_24k_zh" / "ASR"
    if language == "en":
        return ZIPFORMER_24K_MULTILANG_ROOT / "zipformer_24k_en" / "ASR"
    raise ValueError(f"Unsupported language: {language}")


@contextmanager
def _prepend_sys_path(paths: list[Path]) -> Iterator[None]:
    old_path = list(sys.path)
    for path in reversed(paths):
        sys.path.insert(0, str(path))
    try:
        yield
    finally:
        sys.path[:] = old_path


def load_recipe_modules(language: str) -> RecipeModules:
    recipe_root = recipe_root_for_language(language)
    zipformer_dir = recipe_root / "zipformer"
    local_dir = recipe_root / "local"

    with _prepend_sys_path([zipformer_dir, local_dir]):
        decode = importlib.import_module("decode")
        train = importlib.import_module("train")
        asr_datamodule = importlib.import_module("asr_datamodule")

    return RecipeModules(
        recipe_root=recipe_root,
        zipformer_dir=zipformer_dir,
        local_dir=local_dir,
        decode=decode,
        train=train,
        asr_datamodule=asr_datamodule,
    )


def load_local_module(language: str, module_name: str):
    recipe_root = recipe_root_for_language(language)
    module_path = recipe_root / "local" / f"{module_name}.py"
    spec = importlib.util.spec_from_file_location(
        f"emilia_{language}_{module_name}", module_path
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load local module {module_name} for {language}")
    module = importlib.util.module_from_spec(spec)
    with _prepend_sys_path([module_path.parent]):
        spec.loader.exec_module(module)
    return module


def normalize_recipe_args(language: str, args: argparse.Namespace) -> argparse.Namespace:
    modules = load_recipe_modules(language)
    return modules.train.normalize_emilia_args(args)


def create_tokenizer(modules: RecipeModules, language: str, args: argparse.Namespace):
    if language.lower() == "zh":
        tokenizer = modules.train.load_tokenizer(args.lang_dir, args.bpe_model)
        args.blank_id = tokenizer.piece_to_id("<blk>")
        args.unk_id = tokenizer.piece_to_id("<unk>")
        args.vocab_size = tokenizer.get_piece_size()
        return tokenizer

    sp = spm.SentencePieceProcessor()
    sp.load(str(args.bpe_model))
    args.blank_id = sp.piece_to_id("<blk>")
    args.unk_id = sp.piece_to_id("<unk>")
    args.vocab_size = sp.get_piece_size()
    return sp


def hyp_to_text(language: str, hyp) -> str:
    if language.lower() == "zh":
        return str(hyp)
    if isinstance(hyp, str):
        return hyp
    return " ".join(hyp)
