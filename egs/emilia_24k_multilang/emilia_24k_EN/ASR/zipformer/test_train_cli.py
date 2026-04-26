#!/usr/bin/env python3

from train import get_parser


def test_valid_interval_default():
    args = get_parser().parse_args([])
    assert args.valid_interval == 20000


def test_valid_interval_override():
    args = get_parser().parse_args(["--valid-interval", "1000"])
    assert args.valid_interval == 1000


if __name__ == "__main__":
    test_valid_interval_default()
    test_valid_interval_override()
    print("ok")
