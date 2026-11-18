#!/usr/bin/env python3
"""Recording overhead and ``verify`` cost on a synthetic project (E5-style).

A real stack end to end: real ``scitex_io.load`` / ``save`` firing clew's io
hooks, clew's session hooks driven exactly as ``@stx.session`` drives them,
the audit-hook capture on, and a real PostgreSQL store (one fresh database
per configuration). Each phase runs in a FRESH interpreter.

Project shape (as the paper's E5 synthetic workload): ``N`` raw ``.npy``
inputs, ``K`` part sessions (part ``i`` sums its ``N/K`` inputs), one total
session (sums the part outputs). Claim ``part`` rests on part 0 (1 run,
``N/K`` inputs); claim ``total`` rests on everything (``K + 1`` runs,
``N + K + 1`` files). Unrelated bulk (to show verify does not scale with the
project): ``B`` extra sessions in the SAME project, each loading ``M`` files
no claim rests on, and a SECOND project in the same store with the same bulk.

    SCITEX_CLEW_BENCH_DSN=postgresql://postgres@127.0.0.1:55961/postgres \\
        python tests/develop/bench_e5_cost.py --out results.json

Columns: ``rec s/session`` = mean wall per recorded session (clew's hooks +
stx.io), ``cpu`` = its process CPU; ``rec ms/input`` = the per-input slope
between the 1-input and the N/K-input part sessions; ``verify s`` =
in-process ``verify_all_claims(strict=True)`` restricted to one claim's
manuscript (no interpreter / import floor).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

HERE = Path(__file__).resolve()
#: The clew source the children import (override to benchmark a snapshot).
SRC = Path(os.environ.get("SCITEX_CLEW_BENCH_SRC") or HERE.parents[2] / "src")

#: name -> (N inputs, K parts, B unrelated sessions, M inputs per unrelated)
CONFIGS = {
    "N1000-K100": (1000, 100, 0, 0),
    "N1000-K10": (1000, 10, 0, 0),
    "N100-K10": (100, 10, 0, 0),
    "N100-K10+bulk": (100, 10, 40, 50),
}


# --------------------------------------------------------------------- child


def _session(root: Path, script: str, loads: list[Path], out: Path, capture: bool):
    """One recorded session: load ``loads`` via stx.io, save their sum."""
    import numpy as np
    import scitex_io
    from scitex_clew._observers import on_session_close, on_session_start

    sid = f"{script}-{uuid.uuid4().hex[:8]}"
    meta = {"project_root": str(root), "cwd": str(root)}
    t0, c0 = time.perf_counter(), time.process_time()
    if capture:
        on_session_start(sid, script_path=str(root / f"{script}.py"), metadata=meta)
    t1 = time.perf_counter()
    total = 0.0
    for path in loads:
        total += float(np.sum(scitex_io.load(str(path))))
    scitex_io.save(np.array([total]), str(out), verbose=False)
    t2 = time.perf_counter()
    if capture:
        on_session_close(status="success", exit_code=0)
    t3 = time.perf_counter()
    return t3 - t0, time.process_time() - c0, t1 - t0, t2 - t1, t3 - t2


def child_record(
    root: Path, n: int, k: int, b: int, m: int, capture: bool, claims: bool
) -> dict:
    """Record the whole project; returns per-session wall/CPU."""
    import scitex_io  # noqa: F401 - registers clew's io hooks (entry points)

    inputs = sorted((root / "data").glob("x*.npy"))[:n]
    per = n // k
    parts, part_paths = [], []
    for i in range(k):
        out = root / "parts" / f"part_{i:04d}.npy"
        loads = inputs[i * per : (i + 1) * per]
        parts.append((len(loads), *_session(root, "calc_part", loads, out, capture)))
        part_paths.append(out)
    total = _session(root, "calc_total", part_paths, root / "total.npy", capture)
    bulk = []
    for j in range(b):
        loads = sorted((root / "bulk").glob(f"b{j:03d}_*.npy"))[:m]
        bulk.append(
            (
                len(loads),
                *_session(
                    root,
                    "calc_bulk",
                    loads,
                    root / "bulk_out" / f"o{j:03d}.npy",
                    capture,
                ),
            )
        )
    if claims:
        import scitex_clew as clew

        clew.add_claim(
            str(root / "paper_part.tex"),
            "value",
            1,
            "x",
            source_file=str(part_paths[0]),
            claim_id="part",
        )
        clew.add_claim(
            str(root / "paper_total.tex"),
            "value",
            1,
            "x",
            source_file=str(root / "total.npy"),
            claim_id="total",
        )
    return {"parts": parts, "total": [k, *total], "bulk": bulk}


def child_verify(root: Path) -> dict:
    """``verify_all_claims(strict=True)`` per claim, timed in-process."""
    from scitex_clew._claim._verify import verify_all_claims

    out = {}
    for name in ("part", "total"):
        t0 = time.perf_counter()
        result = verify_all_claims(str(root / f"paper_{name}.tex"), strict=True)
        out[name] = {
            "seconds": time.perf_counter() - t0,
            "exit_code": result.exit_code,
            "total": result.total,
        }
    return out


def child_main(argv: list[str]) -> None:
    mode, root = argv[0], Path(argv[1])
    os.chdir(root)
    if mode == "record":
        n, k, b, m, capture, claims = (int(x) for x in argv[2:8])
        print(json.dumps(child_record(root, n, k, b, m, bool(capture), bool(claims))))
    else:
        print(json.dumps(child_verify(root)))


# -------------------------------------------------------------------- parent


def _child_env(dsn: str, root: Path, extra: dict | None = None) -> dict:
    """Explicit allowlist env for the child (never os.environ wholesale)."""
    env = {
        "HOME": os.environ.get("HOME", "/"),
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "LANG": "C.UTF-8",
        "PYTHONPATH": str(SRC),
        "SCITEX_STORE_DSN": dsn,
        "SCITEX_SESSION_PROJECT_ROOT": str(root),
        # The per-session recording journal (clew >= 0.31) stays with the
        # bench, never in the user's ~/.scitex.
        "SCITEX_CLEW_JOURNAL_DIR": str(root.parent / "journal"),
    }
    env.update(extra or {})
    return env


def _run_child(args: list[str], env: dict, cwd: Path) -> dict:
    out = subprocess.run(
        [sys.executable, str(HERE), "--child", *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=cwd,
        check=False,
    )
    if out.returncode != 0:
        raise RuntimeError(f"child {args[:1]} failed:\n{out.stderr[-4000:]}")
    return json.loads(out.stdout.strip().splitlines()[-1])


def _make_project(root: Path, n: int, b: int, m: int) -> None:
    import numpy as np

    for sub in ("data", "parts", "bulk", "bulk_out"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    (root / "pyproject.toml").write_text("[project]\nname='bench'\n")
    for name in ("calc_part.py", "calc_total.py", "calc_bulk.py"):
        (root / name).write_text("# bench script\n")
    for name in ("paper_part.tex", "paper_total.tex"):
        (root / name).write_text("x = 1\n")
    rng = np.random.default_rng(0)
    for i in range(n):
        np.save(root / "data" / f"x{i:05d}.npy", rng.random(128))
    for j in range(b):
        for i in range(m):
            np.save(root / "bulk" / f"b{j:03d}_{i:03d}.npy", rng.random(128))


def _fresh_database(admin_dsn: str) -> str:
    import psycopg

    name = f"clew_bench_{uuid.uuid4().hex[:10]}"
    with psycopg.connect(admin_dsn, autocommit=True) as conn:
        conn.execute(f'CREATE DATABASE "{name}"')
    return f"{admin_dsn.rsplit('/', 1)[0]}/{name}"


def run_config(name: str, base: Path, admin_dsn: str, capture_env: dict) -> dict:
    n, k, b, m = CONFIGS[name]
    dsn = _fresh_database(admin_dsn)
    root = base / name / "proj"
    _make_project(root, n, b, m)
    env = _child_env(dsn, root, capture_env)
    record = _run_child(
        ["record", str(root), str(n), str(k), str(b), str(m), "1", "1"], env, root
    )
    if b:
        other = base / name / "other"
        _make_project(other, n, b, m)
        _run_child(
            ["record", str(other), str(n), str(k), str(b), str(m), "1", "0"],
            _child_env(dsn, other, capture_env),
            other,
        )
    verify = _run_child(["verify", str(root)], env, root)
    sessions = record["parts"] + [record["total"]] + record["bulk"]
    walls = [s[1] for s in sessions]
    cpus = [s[2] for s in sessions]
    hooks = [s[3] + s[5] for s in sessions]
    return {
        "config": name,
        "sessions": len(sessions),
        "inputs": sum(s[0] for s in sessions),
        "record_wall_s": sum(walls),
        "record_cpu_s": sum(cpus),
        "record_s_per_session": sum(walls) / len(walls),
        "record_ms_per_input": 1e3 * sum(walls) / max(1, sum(s[0] for s in sessions)),
        "hooks_s_per_session": sum(hooks) / len(hooks),
        "verify": verify,
    }


#: Cold single-session modes: (label, session hooks on?, extra env).
COLD_MODES = (
    ("on", True, {}),
    ("no-hooks", False, {}),
    ("knob-off", True, {"SCITEX_CLEW_CAPTURE": "0"}),
)


def run_cold(base: Path, admin_dsn: str, n: int, repeats: int) -> dict:
    """Wall of a whole fresh interpreter running ONE session of ``n`` loads.

    The E5 per-session unit: interpreter start, imports, store open, the
    session and its close. ``no-hooks`` skips clew's session hooks (stx.io
    still fires clew's io hooks, which find no tracker); ``knob-off`` keeps
    the hooks and sets the whole-capture off switch.
    """
    import statistics

    root = base / f"cold-{n}"
    _make_project(root, n, 0, 0)
    out = {}
    for label, hooks, extra in COLD_MODES:
        env = _child_env(_fresh_database(admin_dsn), root, extra)
        walls = []
        for _ in range(repeats + 1):  # first = warm-up (creates the tables)
            t0 = time.perf_counter()
            argv = ["record", str(root), str(n), "1", "0", "0", str(int(hooks)), "0"]
            _run_child(argv, env, root)
            walls.append(time.perf_counter() - t0)
        out[label] = statistics.median(walls[1:])
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--configs", nargs="*", default=list(CONFIGS))
    parser.add_argument("--base", default="/scratch/ywatanabe/clew-e5/bench")
    parser.add_argument("--out", default=None)
    parser.add_argument("--label", default="")
    parser.add_argument("--cold", nargs="*", type=int, default=[10, 1000])
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()
    admin_dsn = os.environ["SCITEX_CLEW_BENCH_DSN"]
    base = Path(args.base) / (args.label or uuid.uuid4().hex[:6])
    cold = {n: run_cold(base, admin_dsn, n, args.repeats) for n in args.cold}
    print(f"{'cold 1 session':<16}" + "".join(f"{m[0]:>11}" for m in COLD_MODES))
    for n, row in cold.items():
        print(
            f"{f'{n} inputs':<16}" + "".join(f"{row[m[0]]:>10.3f}s" for m in COLD_MODES)
        )
    rows = [run_config(c, base, admin_dsn, {}) for c in args.configs]
    print(
        f"{'config':<16}{'sess':>6}{'inputs':>8}{'rec s':>9}{'rec cpu':>9}"
        f"{'s/sess':>8}{'hooks':>8}{'ms/in':>8}{'verify part':>13}{'verify total':>14}"
    )
    for r in rows:
        v = r["verify"]
        print(
            f"{r['config']:<16}{r['sessions']:>6}{r['inputs']:>8}"
            f"{r['record_wall_s']:>9.2f}{r['record_cpu_s']:>9.2f}"
            f"{r['record_s_per_session']:>8.3f}{r['hooks_s_per_session']:>8.3f}"
            f"{r['record_ms_per_input']:>8.2f}"
            f"{v['part']['seconds']:>11.3f}/{v['part']['exit_code']}"
            f"{v['total']['seconds']:>12.3f}/{v['total']['exit_code']}"
        )
    if args.out:
        Path(args.out).write_text(json.dumps({"cold": cold, "configs": rows}, indent=2))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--child":
        child_main(sys.argv[2:])
    else:
        main()
