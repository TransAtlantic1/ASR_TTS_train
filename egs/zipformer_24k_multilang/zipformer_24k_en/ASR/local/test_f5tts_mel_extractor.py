#!/usr/bin/env python3

import math

import torch

from f5tts_mel_extractor import F5TTSMelConfig, F5TTSMelExtractor


def make_sine_wave(sample_rate: int, duration: float = 0.25) -> torch.Tensor:
    num_samples = int(sample_rate * duration)
    t = torch.arange(num_samples, dtype=torch.float32) / sample_rate
    return torch.sin(2 * math.pi * 440.0 * t)


def test_extract_24k_does_not_create_resampler():
    extractor = F5TTSMelExtractor(F5TTSMelConfig(device="cpu"))
    features = extractor.extract(make_sine_wave(24000), sampling_rate=24000)

    assert features.shape[1] == 100
    assert extractor._resamplers == {}


def test_extract_32k_reuses_cached_resampler():
    extractor = F5TTSMelExtractor(F5TTSMelConfig(device="cpu"))

    first = extractor.extract(make_sine_wave(32000), sampling_rate=32000)
    cached = extractor._resamplers[(32000, 24000, "cpu")]
    second = extractor.extract(make_sine_wave(32000), sampling_rate=32000)

    assert first.shape[1] == 100
    assert second.shape[1] == 100
    assert extractor._resamplers[(32000, 24000, "cpu")] is cached


def test_extract_44100_creates_distinct_resampler_key():
    extractor = F5TTSMelExtractor(F5TTSMelConfig(device="cpu"))

    features = extractor.extract(make_sine_wave(44100), sampling_rate=44100)

    assert features.shape[1] == 100
    assert (44100, 24000, "cpu") in extractor._resamplers


if __name__ == "__main__":
    test_extract_24k_does_not_create_resampler()
    test_extract_32k_reuses_cached_resampler()
    test_extract_44100_creates_distinct_resampler_key()
    print("ok")
