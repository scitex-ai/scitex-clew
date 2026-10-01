"""Real optional-GUI import failures remain explicit; internal defects propagate."""

import os
import subprocess
import sys

import pytest


@pytest.mark.parametrize(
    "missing,module,operation",
    [
        ("scitex_sdk", "scitex_clew._django.apps", ""),
        ("scitex_sdk", "scitex_clew._django.services.project_files", ""),
        ("scitex_sdk", "scitex_clew._django.services.project_store", ""),
        ("django", "scitex_clew._django.apps", ""),
        ("django", "scitex_clew._django.settings", ""),
        ("django", "scitex_clew._django.models", ""),
        ("django", "scitex_clew._django.migrations.0001_initial", ""),
        ("django", "scitex_clew._django.urls", ""),
        ("psycopg", "scitex_clew._django.services.worker", "target.execute({})"),
    ],
)
def test_missing_gui_dependency_explains_extra_without_breaking_core(
    tmp_path, missing, module, operation
):
    program = f"""
import importlib, importlib.abc, sys
import scitex_clew
assert scitex_clew.__version__
class MissingDependency(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == {missing!r}:
            raise ModuleNotFoundError('absent optional dependency', name=fullname)
sys.meta_path.insert(0, MissingDependency())
try:
    target = importlib.import_module({module!r})
    {operation or 'pass'}
except ModuleNotFoundError as error:
    assert error.name == {missing!r}
    assert 'scitex-clew[gui]' in str(error), str(error)
    assert isinstance(error.__cause__, ModuleNotFoundError)
else:
    raise AssertionError('Missing dependency must not return a partial GUI')
"""
    run_program(program, tmp_path)


def test_internal_sdk_import_failure_is_not_mislabeled_as_missing_extra(tmp_path):
    program = """
import importlib, importlib.abc, sys
import scitex_clew
class BrokenSDK(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'scitex_sdk':
            raise ModuleNotFoundError('broken SDK implementation', name='sdk_internal_dependency')
sys.meta_path.insert(0, BrokenSDK())
try:
    importlib.import_module('scitex_clew._django.apps')
except ModuleNotFoundError as error:
    assert error.name == 'sdk_internal_dependency'
    assert str(error) == 'broken SDK implementation'
    assert 'scitex-clew[gui]' not in str(error)
else:
    raise AssertionError('An internal defect must propagate')
"""
    run_program(program, tmp_path)


def test_app_config_keeps_the_actual_sdk_framework_base():
    from django.apps import AppConfig
    from scitex_sdk.app import embed
    from scitex_clew._django.apps import ClewAppConfig

    assert ClewAppConfig.__bases__ == (embed.ScitexAppConfig,)
    assert issubclass(ClewAppConfig, AppConfig)
    assert type(AppConfig.create("scitex_clew._django")) is ClewAppConfig
    assert (ClewAppConfig.name, ClewAppConfig.label) == ("scitex_clew._django", "clew_app")


def run_program(program, tmp_path):
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("SCITEX_")
        and key not in {"DJANGO_SETTINGS_MODULE", "COVERAGE_PROCESS_START"}
    }
    environment.update(
        SCITEX_DIR=str(tmp_path / "scitex-state"),
        PYTHONDONTWRITEBYTECODE="1",
    )
    completed = subprocess.run(
        [sys.executable, "-P", "-c", program],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
