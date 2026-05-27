#!/usr/bin/env python3

from pathlib import Path

from run_eval import eligible_iters, resolve_watch_dir


def touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("")


def test_resolve_watch_dir_prefers_latest_run_dir(tmp_path: Path):
    base = tmp_path / "exp"
    (base / "run-001").mkdir(parents=True)
    (base / "run-002").mkdir(parents=True)
    resolved = resolve_watch_dir(str(base), auto_resolve_run_dir=True)
    assert resolved == base / "run-002"


def test_eligible_iters_with_averaged_model(tmp_path: Path):
    exp_dir = tmp_path / "exp"
    for value in (5000, 10000, 15000, 20000):
        touch(exp_dir / f"checkpoint-{value}.pt")

    assert eligible_iters(exp_dir, avg=3, decode_every_n=5000, start_iter=0, use_averaged_model=False) == [
        15000,
        20000,
    ]
    assert eligible_iters(exp_dir, avg=3, decode_every_n=5000, start_iter=0, use_averaged_model=True) == [
        20000
    ]


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        test_resolve_watch_dir_prefers_latest_run_dir(tmp_path)
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        test_eligible_iters_with_averaged_model(tmp_path)
