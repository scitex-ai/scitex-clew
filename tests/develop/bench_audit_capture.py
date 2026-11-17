#!/usr/bin/env python3
"""Overhead of clew's file-access audit hook on a 10k ``open()`` loop.

Each mode runs in a FRESH interpreter (an audit hook cannot be removed), so
the baseline really has no hook. Needs a writable store (``SCITEX_STORE_DSN``)
for the modes with an active session.

    python tests/develop/bench_audit_capture.py            # prints a table

Modes
-----
baseline        no hook installed
inactive        hook installed, no session active (between sessions)
active-inside   session active, the SAME project file opened 10k times
                (recorded once, then the cached fast path)
active-outside  session active, a file OUTSIDE the project opened 10k times
active-many     session active, 10k DISTINCT project files (each one hashed
                at open; all recorded in ONE store transaction at close —
                "close s" column)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

N = 10_000

CHILD = r"""
import json, os, sys, time, uuid
from pathlib import Path
mode, root, outside, n = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3]), int(sys.argv[4])
target = root / "data" / "x.txt"
if mode != "baseline":
    from scitex_clew import _capture
    from scitex_clew._tracker import start_tracking, stop_tracking
    _capture._install_hook()
if mode.startswith("active"):
    tracker = start_tracking(uuid.uuid4().hex, script_path=str(root / "s.py"))
    _capture.activate(tracker, script_path=str(root / "s.py"),
                      metadata={"project_root": str(root)})
if mode == "active-outside":
    target = outside
if mode == "active-many":
    paths = [root / "many" / f"f{i}.txt" for i in range(n)]
else:
    paths = [target] * n
t0 = time.perf_counter()
for p in paths:
    with open(p) as f:
        pass
dt = time.perf_counter() - t0
close = 0.0
if mode.startswith("active"):
    t1 = time.perf_counter()
    _capture.finish(tracker)
    close = time.perf_counter() - t1
    stop_tracking()
print(json.dumps({"mode": mode, "seconds": dt, "us_per_open": dt / n * 1e6,
                  "close_seconds": close}))
"""


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root, outside = Path(tmp) / "proj", Path(tmp) / "outside.txt"
        (root / "data").mkdir(parents=True)
        (root / "many").mkdir()
        (root / "data" / "x.txt").write_text("x\n")
        outside.write_text("y\n")
        for i in range(N):
            (root / "many" / f"f{i}.txt").write_text(f"{i}\n")
        rows = []
        for mode in (
            "baseline",
            "inactive",
            "active-inside",
            "active-outside",
            "active-many",
        ):
            out = subprocess.run(
                [sys.executable, "-c", CHILD, mode, str(root), str(outside), str(N)],
                capture_output=True,
                text=True,
                check=True,
            )
            rows.append(json.loads(out.stdout.strip().splitlines()[-1]))
    base = rows[0]["us_per_open"]
    print(
        f"{'mode':<16}{'loop s':>10}{'us/open':>10}{'overhead us':>13}"
        f"{'close s':>10}"
    )
    for r in rows:
        print(
            f"{r['mode']:<16}{r['seconds']:>10.4f}{r['us_per_open']:>10.2f}"
            f"{r['us_per_open'] - base:>13.2f}{r['close_seconds']:>10.3f}"
        )


if __name__ == "__main__":
    main()
