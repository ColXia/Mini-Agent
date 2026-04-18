from __future__ import annotations

import importlib
from pathlib import Path

import pytest


_RUNTIME_DIR = Path(__file__).resolve().parents[1] / "src" / "mini_agent" / "runtime"
_SPECIAL_CASE_WRAPPERS = {"tooling.py"}


def _runtime_compat_wrapper_modules() -> list[str]:
    modules: list[str] = []
    for path in sorted(_RUNTIME_DIR.glob("*.py")):
        if path.name in {"__init__.py", *_SPECIAL_CASE_WRAPPERS}:
            continue
        text = path.read_text(encoding="utf-8")
        if "Compatibility re-export for" in text and "_COMPAT_EXPORTS" in text:
            modules.append(f"mini_agent.runtime.{path.stem}")
    return modules


_LAZY_COMPAT_MODULES = _runtime_compat_wrapper_modules()


def _reset_lazy_export(module_name: str):
    module = importlib.import_module(module_name)
    attr_name = next(iter(module._COMPAT_EXPORTS))
    module.__dict__.pop(attr_name, None)
    return module, attr_name


@pytest.mark.parametrize("module_name", _LAZY_COMPAT_MODULES)
def test_runtime_compat_wrapper_resolves_exports_lazily(module_name: str) -> None:
    module, attr_name = _reset_lazy_export(module_name)

    assert attr_name not in module.__dict__

    resolved = getattr(module, attr_name)

    assert resolved is not None
    assert module.__dict__[attr_name] is resolved


def test_runtime_compat_wrappers_use_lazy_exports_by_default() -> None:
    offenders: list[str] = []
    for path in sorted(_RUNTIME_DIR.glob("*.py")):
        if path.name == "__init__.py":
            continue
        text = path.read_text(encoding="utf-8")
        if "Compatibility re-export for" not in text or path.name in _SPECIAL_CASE_WRAPPERS:
            continue
        if "_COMPAT_EXPORTS" not in text:
            offenders.append(path.name)

    assert offenders == []
