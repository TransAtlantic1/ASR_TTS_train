# Jellycat VAD Long-Audio Sample Progress

## 2026-05-06 UTC

- User requested 10 audio files needing VAD copied into `Jellycat/sample/long_audio`, avoiding duplicate podcasts where possible.
- User clarified planning files should be written under `Jellycat/sample/`, not the dataset root.
- Checked `git status --short`; repository already has many unrelated changes outside this task.
- Confirmed `Jellycat/sample/long_audio` exists and is empty.
- Located ZH/EN pre-VAD candidate JSONLs.
- Started a first sampler, then stopped PID `157815` because it checked source audio existence for every candidate row and was too slow on the external filesystem.
- Next sampler will select candidates first, then verify/copy only the final 10 source FLACs.
- Added `Jellycat/sample/sample_vad_long_audio.py`, a task-local sampler that uses random candidate line numbers, enforces unique podcasts, copies FLACs, and writes metadata.
- Ran `python3 -m py_compile Jellycat/sample/sample_vad_long_audio.py` successfully.
- Ran `python3 Jellycat/sample/sample_vad_long_audio.py`; it copied 10 FLACs into `Jellycat/sample/long_audio`.
- Verified output metadata: 10 rows, 10 unique podcasts, ZH/EN split is 5/5, copied files all exist, duration range is 32.03s to 40.32s, and no audio-info errors were reported.
- Added `Jellycat/sample/.gitignore` for Python bytecode/runtime cache files.
- Received stop-hook prompt reporting planning incomplete. Re-read `Jellycat/sample/task_plan.md`; all four task phases are marked complete. No additional copy/sampling work remains.
