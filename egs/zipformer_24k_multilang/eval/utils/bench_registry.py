#!/usr/bin/env python3

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Sequence


ZIPFORMER_24K_MULTILANG_ROOT = Path(__file__).resolve().parents[2]
ICEFALL_ROOT = ZIPFORMER_24K_MULTILANG_ROOT.parents[1]
PUBLIC_EVAL_ROOT = Path(
    "/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/public/eval"
)
BENCH2_ROOT = PUBLIC_EVAL_ROOT
RESULTS_ROOT = ZIPFORMER_24K_MULTILANG_ROOT / "eval" / "results"


@dataclass(frozen=True)
class DatasetSpec:
    dataset_id: str
    language: str
    difficulty: str
    description: str
    source_url: str
    manual_download: bool
    prep_kind: str
    prepared_relpath: str
    tags: Sequence[str] = field(default_factory=tuple)
    raw_download_subdir: str = ""
    existing_cut_candidates: Sequence[str] = field(default_factory=tuple)
    existing_prepared_dataset_ids: Sequence[str] = field(default_factory=tuple)
    speechio_official_norm: bool = False
    extra: Dict[str, str] = field(default_factory=dict)

    def dataset_root(self, bench_root: Path | None = None) -> Path:
        root = BENCH2_ROOT if bench_root is None else Path(bench_root)
        return root / self.dataset_id

    def prepared_cut_path(self, bench_root: Path | None = None) -> Path:
        return self.dataset_root(bench_root) / "fbank" / f"{self.dataset_id}_cuts.jsonl.gz"


ZH_DATASETS: Dict[str, DatasetSpec] = {
    "thchs30_test": DatasetSpec(
        dataset_id="thchs30_test",
        language="zh",
        difficulty="medium",
        description="THCHS-30 clean test split.",
        source_url="https://www.openslr.org/18",
        manual_download=False,
        prep_kind="thchs30_clean",
        prepared_relpath="fbank/thchs30_test/thchs30_test_cuts.jsonl.gz",
        tags=("legacy", "open", "clean"),
        raw_download_subdir="thchs30",
    ),
    "thchs30_noise_white": DatasetSpec(
        dataset_id="thchs30_noise_white",
        language="zh",
        difficulty="hard",
        description="THCHS-30 white-noise 0 dB test split.",
        source_url="https://www.openslr.org/18",
        manual_download=False,
        prep_kind="thchs30_noise",
        prepared_relpath="fbank/thchs30_noise_white/thchs30_noise_white_cuts.jsonl.gz",
        tags=("legacy", "open", "noise"),
        raw_download_subdir="thchs30",
    ),
    "thchs30_noise_car": DatasetSpec(
        dataset_id="thchs30_noise_car",
        language="zh",
        difficulty="hard",
        description="THCHS-30 car-noise 0 dB test split.",
        source_url="https://www.openslr.org/18",
        manual_download=False,
        prep_kind="thchs30_noise",
        prepared_relpath="fbank/thchs30_noise_car/thchs30_noise_car_cuts.jsonl.gz",
        tags=("legacy", "open", "noise"),
        raw_download_subdir="thchs30",
    ),
    "thchs30_noise_cafe": DatasetSpec(
        dataset_id="thchs30_noise_cafe",
        language="zh",
        difficulty="hard",
        description="THCHS-30 cafe-noise 0 dB test split.",
        source_url="https://www.openslr.org/18",
        manual_download=False,
        prep_kind="thchs30_noise",
        prepared_relpath="fbank/thchs30_noise_cafe/thchs30_noise_cafe_cuts.jsonl.gz",
        tags=("legacy", "open", "noise"),
        raw_download_subdir="thchs30",
    ),
    "AISHELL1_TEST": DatasetSpec(
        dataset_id="AISHELL1_TEST",
        language="zh",
        difficulty="medium",
        description="AISHELL-1 official test split.",
        source_url="https://www.openslr.org/33",
        manual_download=False,
        prep_kind="aishell_eval",
        prepared_relpath="fbank/AISHELL1_TEST/AISHELL1_TEST_cuts.jsonl.gz",
        tags=("academic", "open"),
        raw_download_subdir="aishell",
        extra={"split": "test"},
    ),
    "AISHELL2_IOS_TEST": DatasetSpec(
        dataset_id="AISHELL2_IOS_TEST",
        language="zh",
        difficulty="medium",
        description="AISHELL-2 iOS test split.",
        source_url="https://www.aishelltech.com/aishell_2",
        manual_download=True,
        prep_kind="aishell2_eval",
        prepared_relpath="fbank/AISHELL2_IOS_TEST/AISHELL2_IOS_TEST_cuts.jsonl.gz",
        tags=("academic", "manual"),
        raw_download_subdir="aishell2",
        extra={"channel": "ios", "split": "test"},
    ),
    "AISHELL2_ANDROID_TEST": DatasetSpec(
        dataset_id="AISHELL2_ANDROID_TEST",
        language="zh",
        difficulty="medium",
        description="AISHELL-2 Android test split.",
        source_url="https://www.aishelltech.com/aishell_2",
        manual_download=True,
        prep_kind="aishell2_eval",
        prepared_relpath="fbank/AISHELL2_ANDROID_TEST/AISHELL2_ANDROID_TEST_cuts.jsonl.gz",
        tags=("academic", "manual"),
        raw_download_subdir="aishell2",
        extra={"channel": "android", "split": "test"},
    ),
    "AISHELL2_MIC_TEST": DatasetSpec(
        dataset_id="AISHELL2_MIC_TEST",
        language="zh",
        difficulty="medium",
        description="AISHELL-2 Mic test split.",
        source_url="https://www.aishelltech.com/aishell_2",
        manual_download=True,
        prep_kind="aishell2_eval",
        prepared_relpath="fbank/AISHELL2_MIC_TEST/AISHELL2_MIC_TEST_cuts.jsonl.gz",
        tags=("academic", "manual"),
        raw_download_subdir="aishell2",
        extra={"channel": "mic", "split": "test"},
    ),
    "ALIMEETING_EVAL_NEAR_FIELD": DatasetSpec(
        dataset_id="ALIMEETING_EVAL_NEAR_FIELD",
        language="zh",
        difficulty="hard",
        description="AliMeeting eval near-field split.",
        source_url="https://www.openslr.org/119",
        manual_download=False,
        prep_kind="alimeeting_split",
        prepared_relpath="fbank/ALIMEETING_EVAL_NEAR_FIELD/ALIMEETING_EVAL_NEAR_FIELD_cuts.jsonl.gz",
        tags=("academic", "open", "meeting"),
        raw_download_subdir="alimeeting",
        extra={"split": "eval", "mic": "ihm"},
    ),
    "ALIMEETING_TEST_NEAR_FIELD": DatasetSpec(
        dataset_id="ALIMEETING_TEST_NEAR_FIELD",
        language="zh",
        difficulty="hard",
        description="AliMeeting test near-field split.",
        source_url="https://www.openslr.org/119",
        manual_download=False,
        prep_kind="alimeeting_split",
        prepared_relpath="fbank/ALIMEETING_TEST_NEAR_FIELD/ALIMEETING_TEST_NEAR_FIELD_cuts.jsonl.gz",
        tags=("academic", "open", "meeting"),
        raw_download_subdir="alimeeting",
        existing_prepared_dataset_ids=("alimeeting_test_near",),
        extra={"split": "test", "mic": "ihm"},
    ),
    "ALIMEETING_EVAL_FAR_FIELD": DatasetSpec(
        dataset_id="ALIMEETING_EVAL_FAR_FIELD",
        language="zh",
        difficulty="hard",
        description="AliMeeting eval far-field split.",
        source_url="https://www.openslr.org/119",
        manual_download=False,
        prep_kind="alimeeting_split",
        prepared_relpath="fbank/ALIMEETING_EVAL_FAR_FIELD/ALIMEETING_EVAL_FAR_FIELD_cuts.jsonl.gz",
        tags=("academic", "open", "meeting"),
        raw_download_subdir="alimeeting",
        extra={"split": "eval", "mic": "sdm"},
    ),
    "ALIMEETING_TEST_FAR_FIELD": DatasetSpec(
        dataset_id="ALIMEETING_TEST_FAR_FIELD",
        language="zh",
        difficulty="hard",
        description="AliMeeting test far-field split.",
        source_url="https://www.openslr.org/119",
        manual_download=False,
        prep_kind="alimeeting_split",
        prepared_relpath="fbank/ALIMEETING_TEST_FAR_FIELD/ALIMEETING_TEST_FAR_FIELD_cuts.jsonl.gz",
        tags=("academic", "open", "meeting"),
        raw_download_subdir="alimeeting",
        existing_prepared_dataset_ids=("alimeeting_test_far",),
        extra={"split": "test", "mic": "sdm"},
    ),
    "wenetspeech_test_net": DatasetSpec(
        dataset_id="wenetspeech_test_net",
        language="zh",
        difficulty="hard",
        description="WenetSpeech TEST_NET imported from the sibling recipe if available.",
        source_url="https://github.com/wenet-e2e/WenetSpeech",
        manual_download=True,
        prep_kind="existing_cut_import",
        prepared_relpath="fbank/wenetspeech_test_net/wenetspeech_test_net_cuts.jsonl.gz",
        tags=("legacy", "manual", "meeting"),
        existing_cut_candidates=(
            "egs/wenetspeech/ASR/data/fbank/cuts_TEST_NET_raw.jsonl.gz",
            "egs/wenetspeech/ASR/data/fbank/cuts_TEST_NET.jsonl.gz",
        ),
    ),
    "wenetspeech_test_meeting": DatasetSpec(
        dataset_id="wenetspeech_test_meeting",
        language="zh",
        difficulty="hard",
        description="WenetSpeech TEST_MEETING imported from the sibling recipe if available.",
        source_url="https://github.com/wenet-e2e/WenetSpeech",
        manual_download=True,
        prep_kind="existing_cut_import",
        prepared_relpath="fbank/wenetspeech_test_meeting/wenetspeech_test_meeting_cuts.jsonl.gz",
        tags=("legacy", "manual", "meeting"),
        existing_cut_candidates=(
            "egs/wenetspeech/ASR/data/fbank/cuts_TEST_MEETING_raw.jsonl.gz",
            "egs/wenetspeech/ASR/data/fbank/cuts_TEST_MEETING.jsonl.gz",
        ),
    ),
    "kespeech_test": DatasetSpec(
        dataset_id="kespeech_test",
        language="zh",
        difficulty="hard",
        description="KeSpeech test split imported from the sibling recipe if available.",
        source_url="https://github.com/KeSpeech/KeSpeech",
        manual_download=True,
        prep_kind="existing_cut_import",
        prepared_relpath="fbank/kespeech_test/kespeech_test_cuts.jsonl.gz",
        tags=("legacy", "manual", "noise"),
        existing_cut_candidates=(
            "egs/multi_zh-hans/ASR/data/fbank/kespeech/kespeech-asr_cuts_test.jsonl.gz",
        ),
    ),
    "kespeech_dev_phase1": DatasetSpec(
        dataset_id="kespeech_dev_phase1",
        language="zh",
        difficulty="hard",
        description="KeSpeech dev_phase1 imported from the sibling recipe if available.",
        source_url="https://github.com/KeSpeech/KeSpeech",
        manual_download=True,
        prep_kind="existing_cut_import",
        prepared_relpath="fbank/kespeech_dev_phase1/kespeech_dev_phase1_cuts.jsonl.gz",
        tags=("legacy", "manual", "noise"),
        existing_cut_candidates=(
            "egs/multi_zh-hans/ASR/data/fbank/kespeech/kespeech-asr_cuts_dev_phase1.jsonl.gz",
        ),
    ),
    "kespeech_dev_phase2": DatasetSpec(
        dataset_id="kespeech_dev_phase2",
        language="zh",
        difficulty="hard",
        description="KeSpeech dev_phase2 imported from the sibling recipe if available.",
        source_url="https://github.com/KeSpeech/KeSpeech",
        manual_download=True,
        prep_kind="existing_cut_import",
        prepared_relpath="fbank/kespeech_dev_phase2/kespeech_dev_phase2_cuts.jsonl.gz",
        tags=("legacy", "manual", "noise"),
        existing_cut_candidates=(
            "egs/multi_zh-hans/ASR/data/fbank/kespeech/kespeech-asr_cuts_dev_phase2.jsonl.gz",
        ),
    ),
}


EN_DATASETS: Dict[str, DatasetSpec] = {
    "LIBRISPEECH_TEST_CLEAN": DatasetSpec(
        dataset_id="LIBRISPEECH_TEST_CLEAN",
        language="en",
        difficulty="medium",
        description="LibriSpeech test-clean split.",
        source_url="https://www.openslr.org/12",
        manual_download=False,
        prep_kind="librispeech_eval",
        prepared_relpath="fbank/LIBRISPEECH_TEST_CLEAN/LIBRISPEECH_TEST_CLEAN_cuts.jsonl.gz",
        tags=("open", "academic"),
        raw_download_subdir="librispeech",
        extra={"split": "test-clean"},
    ),
    "LIBRISPEECH_TEST_OTHER": DatasetSpec(
        dataset_id="LIBRISPEECH_TEST_OTHER",
        language="en",
        difficulty="hard",
        description="LibriSpeech test-other split.",
        source_url="https://www.openslr.org/12",
        manual_download=False,
        prep_kind="librispeech_eval",
        prepared_relpath="fbank/LIBRISPEECH_TEST_OTHER/LIBRISPEECH_TEST_OTHER_cuts.jsonl.gz",
        tags=("open", "academic"),
        raw_download_subdir="librispeech",
        extra={"split": "test-other"},
    ),
    "TEDLIUM_RELEASE3_LEGACY_DEV": DatasetSpec(
        dataset_id="TEDLIUM_RELEASE3_LEGACY_DEV",
        language="en",
        difficulty="medium",
        description="TEDLIUM Release 3 legacy dev split.",
        source_url="https://www.openslr.org/51",
        manual_download=False,
        prep_kind="tedlium_eval",
        prepared_relpath="fbank/TEDLIUM_RELEASE3_LEGACY_DEV/TEDLIUM_RELEASE3_LEGACY_DEV_cuts.jsonl.gz",
        tags=("open", "academic"),
        raw_download_subdir="tedlium3",
        extra={"split": "dev"},
    ),
    "TEDLIUM_RELEASE3_LEGACY_TEST": DatasetSpec(
        dataset_id="TEDLIUM_RELEASE3_LEGACY_TEST",
        language="en",
        difficulty="hard",
        description="TEDLIUM Release 3 legacy test split.",
        source_url="https://www.openslr.org/51",
        manual_download=False,
        prep_kind="tedlium_eval",
        prepared_relpath="fbank/TEDLIUM_RELEASE3_LEGACY_TEST/TEDLIUM_RELEASE3_LEGACY_TEST_cuts.jsonl.gz",
        tags=("open", "academic"),
        raw_download_subdir="tedlium3",
        extra={"split": "test"},
    ),
    "GIGASPEECH_V1.0.0_DEV": DatasetSpec(
        dataset_id="GIGASPEECH_V1.0.0_DEV",
        language="en",
        difficulty="medium",
        description="GigaSpeech v1.0.0 DEV split.",
        source_url="https://github.com/SpeechColab/GigaSpeech",
        manual_download=True,
        prep_kind="gigaspeech_eval",
        prepared_relpath="fbank/GIGASPEECH_V1.0.0_DEV/GIGASPEECH_V1.0.0_DEV_cuts.jsonl.gz",
        tags=("open", "credentialed"),
        raw_download_subdir="gigaspeech",
        extra={"split": "DEV"},
    ),
    "GIGASPEECH_V1.0.0_TEST": DatasetSpec(
        dataset_id="GIGASPEECH_V1.0.0_TEST",
        language="en",
        difficulty="hard",
        description="GigaSpeech v1.0.0 TEST split.",
        source_url="https://github.com/SpeechColab/GigaSpeech",
        manual_download=True,
        prep_kind="gigaspeech_eval",
        prepared_relpath="fbank/GIGASPEECH_V1.0.0_TEST/GIGASPEECH_V1.0.0_TEST_cuts.jsonl.gz",
        tags=("open", "credentialed"),
        raw_download_subdir="gigaspeech",
        extra={"split": "TEST"},
    ),
    "VOXPOPULI_V1.0_EN_DEV": DatasetSpec(
        dataset_id="VOXPOPULI_V1.0_EN_DEV",
        language="en",
        difficulty="medium",
        description="VoxPopuli v1.0 English dev split.",
        source_url="https://github.com/facebookresearch/voxpopuli",
        manual_download=False,
        prep_kind="voxpopuli_eval",
        prepared_relpath="fbank/VOXPOPULI_V1.0_EN_DEV/VOXPOPULI_V1.0_EN_DEV_cuts.jsonl.gz",
        tags=("open", "academic"),
        raw_download_subdir="voxpopuli",
        extra={"split": "dev"},
    ),
    "VOXPOPULI_V1.0_EN_TEST": DatasetSpec(
        dataset_id="VOXPOPULI_V1.0_EN_TEST",
        language="en",
        difficulty="hard",
        description="VoxPopuli v1.0 English test split.",
        source_url="https://github.com/facebookresearch/voxpopuli",
        manual_download=False,
        prep_kind="voxpopuli_eval",
        prepared_relpath="fbank/VOXPOPULI_V1.0_EN_TEST/VOXPOPULI_V1.0_EN_TEST_cuts.jsonl.gz",
        tags=("open", "academic"),
        raw_download_subdir="voxpopuli",
        extra={"split": "test"},
    ),
    "VOXPOPULI_V1.0_EN_ACCENTED_TEST": DatasetSpec(
        dataset_id="VOXPOPULI_V1.0_EN_ACCENTED_TEST",
        language="en",
        difficulty="hard",
        description="VoxPopuli v1.0 English accented test split.",
        source_url="https://github.com/facebookresearch/voxpopuli",
        manual_download=False,
        prep_kind="voxpopuli_accented_eval",
        prepared_relpath="fbank/VOXPOPULI_V1.0_EN_ACCENTED_TEST/VOXPOPULI_V1.0_EN_ACCENTED_TEST_cuts.jsonl.gz",
        tags=("open", "accented"),
        raw_download_subdir="voxpopuli",
        extra={"split": "test"},
    ),
    "COMMON_VOICE_V11.0_DEV": DatasetSpec(
        dataset_id="COMMON_VOICE_V11.0_DEV",
        language="en",
        difficulty="medium",
        description="Common Voice v11.0 English dev split.",
        source_url="https://commonvoice.mozilla.org/en/datasets",
        manual_download=False,
        prep_kind="commonvoice_eval",
        prepared_relpath="fbank/COMMON_VOICE_V11.0_DEV/COMMON_VOICE_V11.0_DEV_cuts.jsonl.gz",
        tags=("open", "academic"),
        raw_download_subdir="commonvoice",
        extra={"split": "dev", "release": "cv-corpus-11.0-2022-09-21"},
    ),
    "COMMON_VOICE_V11.0_TEST": DatasetSpec(
        dataset_id="COMMON_VOICE_V11.0_TEST",
        language="en",
        difficulty="hard",
        description="Common Voice v11.0 English test split.",
        source_url="https://commonvoice.mozilla.org/en/datasets",
        manual_download=False,
        prep_kind="commonvoice_eval",
        prepared_relpath="fbank/COMMON_VOICE_V11.0_TEST/COMMON_VOICE_V11.0_TEST_cuts.jsonl.gz",
        tags=("open", "academic"),
        raw_download_subdir="commonvoice",
        extra={"split": "test", "release": "cv-corpus-11.0-2022-09-21"},
    ),
}


PRESETS: Dict[str, List[str]] = {
    "zh-academic-v1": [
        "AISHELL1_TEST",
        "AISHELL2_IOS_TEST",
        "AISHELL2_ANDROID_TEST",
        "AISHELL2_MIC_TEST",
        "ALIMEETING_EVAL_NEAR_FIELD",
        "ALIMEETING_TEST_NEAR_FIELD",
        "ALIMEETING_EVAL_FAR_FIELD",
        "ALIMEETING_TEST_FAR_FIELD",
    ],
    "zh-legacy-open-v1": [
        "thchs30_test",
        "thchs30_noise_white",
        "thchs30_noise_car",
        "thchs30_noise_cafe",
    ],
    "zh-import-v1": [
        "wenetspeech_test_net",
        "wenetspeech_test_meeting",
        "kespeech_test",
        "kespeech_dev_phase1",
        "kespeech_dev_phase2",
    ],
    "en-open-v1": [
        "VOXPOPULI_V1.0_EN_DEV",
        "VOXPOPULI_V1.0_EN_TEST",
        "VOXPOPULI_V1.0_EN_ACCENTED_TEST",
        "COMMON_VOICE_V11.0_DEV",
        "COMMON_VOICE_V11.0_TEST",
    ],
}


def registry_for_language(language: str) -> Dict[str, DatasetSpec]:
    language = language.lower()
    if language == "zh":
        return ZH_DATASETS
    if language == "en":
        return EN_DATASETS
    raise ValueError(f"Unsupported language: {language}")


def available_dataset_ids(language: str) -> List[str]:
    return sorted(registry_for_language(language))


def resolve_dataset_ids(
    language: str,
    dataset_ids: Sequence[str] | None = None,
    preset_names: Sequence[str] | None = None,
) -> List[str]:
    registry = registry_for_language(language)
    resolved: List[str] = []

    if preset_names:
        for preset_name in preset_names:
            if preset_name not in PRESETS:
                raise ValueError(f"Unknown preset: {preset_name}")
            resolved.extend(PRESETS[preset_name])

    if dataset_ids:
        resolved.extend(dataset_ids)

    if not resolved:
        raise ValueError("No dataset IDs or presets were provided.")

    deduped: List[str] = []
    seen = set()
    for dataset_id in resolved:
        if dataset_id not in registry:
            raise ValueError(f"Unknown dataset ID for {language}: {dataset_id}")
        if dataset_id not in seen:
            seen.add(dataset_id)
            deduped.append(dataset_id)
    return deduped


def specs_for(language: str, dataset_ids: Sequence[str]) -> List[DatasetSpec]:
    registry = registry_for_language(language)
    return [registry[dataset_id] for dataset_id in dataset_ids]
