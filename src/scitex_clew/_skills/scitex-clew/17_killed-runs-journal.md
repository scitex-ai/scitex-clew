---
description: |
  [TOPIC] Killed runs (recording journal)
  [DETAILS] A recorded run killed before close (SIGKILL, OOM, container/agent-harness timeout, SIGTERM/SIGHUP) keeps the rows it recorded: each session appends them to a per-session journal, and the next session start / clew command replays it and closes the run as `killed`. How each ending is recorded, idempotency, concurrency, what a killed run does NOT record, `clew recover-journals`, and the env vars.
tags: [scitex-clew-killed-runs-journal]
---

# Killed runs keep their record (journal)

Agent harnesses kill runs on timeouts. Each session therefore ALSO appends
every queued row — and every `open()` read the capture hashed — to a
per-session journal as it happens (`$SCITEX_CLEW_JOURNAL_DIR`, default
`~/.scitex/clew/journal/<host>/<session>.<pid>.jsonl`, mode 0600): one
`os.write` per row, no `fsync` (the page cache survives the process's death;
a power cut is what the store's commit is for). The owner holds an `flock`
on it; the kernel drops it when the process dies, however it dies.

| How the run ends | Recorded | Run status |
|---|---|---|
| closed (`@stx.session` return/raise, `clew.session` exit) | everything; journal deleted | `success` / `error` |
| interpreter exits with the session open (`sys.exit`, uncaught `KeyboardInterrupt`) | everything (`atexit` runs the close) | `incomplete` |
| `SIGTERM` / `SIGHUP` (default action) | handler replays the journal, then re-raises the signal (the process still dies of it) | `killed`, `exit_code = -signum`, `metadata.clew_recovery.signal` |
| `SIGKILL`, OOM, container stop | nothing runs; the NEXT session start or `clew` command on this machine replays the journal | `killed` |

Replay writes the rows the dead process never committed, records the
captured reads a close would have, binds producers, closes the run and
attaches `metadata["clew_recovery"]`; it is idempotent (upserts on the row
identity), skips journals of LIVE processes (lock held) and of OTHER stores
(DSN fingerprint), and is also `clew recover-journals [--dry-run]` /
`clew.recover_journals()`. `killed` and `incomplete` are failed runs for
`verify` — their files are not evidence — but their rows show what they read
and wrote up to the kill. Not recorded for a killed run: bytes of files it
only opened for WRITING (hashed at close; a killed run's output may be
partial) — listed in `clew_recovery.unhashed_writes`; modules first imported
after start; symlink metadata. `SCITEX_CLEW_JOURNAL=0` turns the journal
(and the signal handlers) off.
