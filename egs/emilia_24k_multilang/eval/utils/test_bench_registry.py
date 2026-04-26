#!/usr/bin/env python3

from bench_registry import PRESETS, available_dataset_ids, resolve_dataset_ids


def test_resolve_dataset_ids_dedupes_without_speechio_expansion():
    resolved = resolve_dataset_ids(
        "zh",
        dataset_ids=["AISHELL1_TEST", "AISHELL1_TEST", "ALIMEETING_TEST_NEAR_FIELD"],
        preset_names=[],
    )
    assert resolved == ["AISHELL1_TEST", "ALIMEETING_TEST_NEAR_FIELD"]
    assert "speechio_zh00000" not in available_dataset_ids("zh")


def test_resolve_zh_academic_preset():
    resolved = resolve_dataset_ids("zh", dataset_ids=[], preset_names=["zh-academic-v1"])
    assert resolved == [
        "AISHELL1_TEST",
        "AISHELL2_IOS_TEST",
        "AISHELL2_ANDROID_TEST",
        "AISHELL2_MIC_TEST",
        "ALIMEETING_EVAL_NEAR_FIELD",
        "ALIMEETING_TEST_NEAR_FIELD",
        "ALIMEETING_EVAL_FAR_FIELD",
        "ALIMEETING_TEST_FAR_FIELD",
    ]


def test_legacy_zh_preset_no_longer_registers_duplicate_alimeeting_test_ids():
    resolved = resolve_dataset_ids("zh", dataset_ids=[], preset_names=["zh-legacy-open-v1"])
    assert resolved == [
        "thchs30_test",
        "thchs30_noise_white",
        "thchs30_noise_car",
        "thchs30_noise_cafe",
    ]
    assert "alimeeting_test_near" not in available_dataset_ids("zh")
    assert "alimeeting_test_far" not in available_dataset_ids("zh")
    assert "alimeeting_test_near" not in PRESETS["zh-legacy-open-v1"]
    assert "alimeeting_test_far" not in PRESETS["zh-legacy-open-v1"]


def test_resolve_en_open_preset():
    resolved = resolve_dataset_ids("en", dataset_ids=[], preset_names=["en-open-v1"])
    assert resolved == [
        "VOXPOPULI_V1.0_EN_DEV",
        "VOXPOPULI_V1.0_EN_TEST",
        "VOXPOPULI_V1.0_EN_ACCENTED_TEST",
        "COMMON_VOICE_V11.0_DEV",
        "COMMON_VOICE_V11.0_TEST",
    ]


if __name__ == "__main__":
    test_resolve_dataset_ids_dedupes_without_speechio_expansion()
    test_resolve_zh_academic_preset()
    test_legacy_zh_preset_no_longer_registers_duplicate_alimeeting_test_ids()
    test_resolve_en_open_preset()
