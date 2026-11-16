#!/usr/bin/env python3
"""The io-hook seam honours ``derived_from`` — real store, real files.

Toy: step 1 writes used.csv and unused.csv; step 2 loads BOTH and saves
result.json. Each file event goes through ``on_io_load`` / ``on_io_save``
with exactly the payload scitex-io sends (``kwargs["derived_from"]`` is a
list of realpaths, present only when the caller declared it).

* declared ``[used.csv]`` -> ``slice(level=2)`` drops unused.csv (and the
  level-1 slice keeps it, because step 2 read it);
* nothing declared -> level 2 equals level 1 (no invented edges);
* the same bytes recorded twice (a figure tool records its image, then the
  ``stx.io.save`` that called it fires its hook) keep the declaration.
"""

from __future__ import annotations

import json
import os

import pytest
from scitex_clew._chain._slice import build_slice
from scitex_clew._observers import on_io_load, on_io_save
from scitex_clew._tracker import start_tracking, stop_tracking


@pytest.fixture(autouse=True)
def _no_claims_export():
    prev = os.environ.get("SCITEX_CLEW_AUTO_EXPORT_CLAIMS")
    os.environ["SCITEX_CLEW_AUTO_EXPORT_CLAIMS"] = "0"
    yield
    if prev is None:
        os.environ.pop("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", None)
    else:
        os.environ["SCITEX_CLEW_AUTO_EXPORT_CLAIMS"] = prev


def _toy(tmp_path, declared):
    """Run the two-step toy through the io hooks; return result.json's path."""
    used, unused = tmp_path / "used.csv", tmp_path / "unused.csv"
    result = tmp_path / "result.json"
    script = tmp_path / "step.py"
    script.write_text("# step\n")

    start_tracking("step1", script_path=str(script))
    for path, rows in ((used, "x\n1\n2\n"), (unused, "x\n9\n")):
        path.write_text(rows)
        on_io_save(path, None, {"track": True})
    stop_tracking()

    start_tracking("step2", script_path=str(script))
    on_io_load(used, None)
    on_io_load(unused, None)
    result.write_text(json.dumps({"n": 2}))
    kwargs = {"track": True}
    if declared is not None:
        kwargs["derived_from"] = [str(p) for p in declared(used, unused)]
    on_io_save(result, {"n": 2}, kwargs)
    stop_tracking()
    return result, unused


def _names(sl):
    return sorted(os.path.basename(p) for p in sl.files)


def test_level1_keeps_the_input_the_run_read_but_did_not_use(tmp_path):
    # Arrange
    result, _ = _toy(tmp_path, declared=lambda used, unused: [used])
    # Act
    sl = build_slice([result], level=1)
    # Assert
    assert _names(sl) == ["result.json", "unused.csv", "used.csv"]


def test_level2_drops_the_undeclared_input(tmp_path):
    # Arrange
    result, _ = _toy(tmp_path, declared=lambda used, unused: [used])
    # Act
    sl = build_slice([result], level=2)
    # Assert
    assert _names(sl) == ["result.json", "used.csv"]


def test_level2_reports_the_dropped_input(tmp_path):
    # Arrange
    result, unused = _toy(tmp_path, declared=lambda used, unused: [used])
    # Act
    sl = build_slice([result], level=2)
    # Assert
    assert sl.dropped_inputs.get("step2") == [str(unused.resolve())]


def test_without_declaration_level2_equals_level1(tmp_path):
    # Arrange
    result, _ = _toy(tmp_path, declared=None)
    # Act
    counts = [build_slice([result], level=lvl).counts() for lvl in (1, 2)]
    # Assert
    assert counts[0] == counts[1]


def test_without_declaration_level2_keeps_every_input(tmp_path):
    # Arrange
    result, _ = _toy(tmp_path, declared=None)
    # Act
    sl = build_slice([result], level=2)
    # Assert
    assert _names(sl) == ["result.json", "unused.csv", "used.csv"]


def _double_record(tmp_path, first, second):
    """Record result.json twice (same bytes) with two payloads; slice level 2."""
    used, unused = tmp_path / "used.csv", tmp_path / "unused.csv"
    used.write_text("x\n1\n")
    unused.write_text("x\n9\n")
    result = tmp_path / "result.json"
    start_tracking("both", script_path=None)
    on_io_load(used, None)
    on_io_load(unused, None)
    result.write_text("{}")
    paths = {"used": str(used), "unused": str(unused)}
    for decl in (first, second):
        kwargs = {"track": True}
        if decl is not None:
            kwargs["derived_from"] = [paths[n] for n in decl]
        on_io_save(result, None, kwargs)
    stop_tracking()
    return _names(build_slice([result], level=2))


def test_undeclared_rerecord_of_same_bytes_keeps_declaration(tmp_path):
    # Arrange
    first, second = ["used"], None
    # Act
    names = _double_record(tmp_path, first, second)
    # Assert
    assert names == ["result.json", "used.csv"]


def test_second_declaration_of_same_bytes_is_unioned(tmp_path):
    # Arrange
    first, second = ["used"], ["unused"]
    # Act
    names = _double_record(tmp_path, first, second)
    # Assert
    assert names == ["result.json", "unused.csv", "used.csv"]


def test_rewritten_bytes_drop_the_old_declaration(tmp_path):
    # Arrange: declared write, then NEW bytes written without a declaration
    used, unused = tmp_path / "used.csv", tmp_path / "unused.csv"
    used.write_text("x\n1\n")
    unused.write_text("x\n9\n")
    result = tmp_path / "result.json"
    start_tracking("rewrite", script_path=None)
    on_io_load(used, None)
    on_io_load(unused, None)
    result.write_text("{}")
    on_io_save(result, None, {"track": True, "derived_from": [str(used)]})
    result.write_text('{"changed": 1}')
    on_io_save(result, None, {"track": True})
    stop_tracking()
    # Act
    sl = build_slice([result], level=2)
    # Assert
    assert _names(sl) == ["result.json", "unused.csv", "used.csv"]
