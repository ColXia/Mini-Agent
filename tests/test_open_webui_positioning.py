"""Positioning guardrails for optional OpenWebUI adapter integration."""

from __future__ import annotations

from pathlib import Path
import re


REPO_ROOT = Path(__file__).resolve().parents[1]
MAIN_BUSINESS_ROOTS = (
    REPO_ROOT / "src" / "mini_agent",
    REPO_ROOT / "src" / "apps" / "agent_studio_gateway",
    REPO_ROOT / "src" / "subprograms",
)
OPENWEBUI_IMPORT_PATTERN = re.compile(r"^\s*(?:from|import)\s+apps\.open_webui\b", re.MULTILINE)
OPENWEBUI_ENDPOINT_PATTERN = re.compile(r"['\"]/v1/(?:chat/completions|models)\b")


def _iter_python_files() -> list[Path]:
    files: list[Path] = []
    for root in MAIN_BUSINESS_ROOTS:
        if not root.exists():
            continue
        files.extend(sorted(root.rglob("*.py")))
    return files


def test_main_business_python_has_no_openwebui_adapter_imports() -> None:
    violations: list[str] = []
    for path in _iter_python_files():
        text = path.read_text(encoding="utf-8")
        if OPENWEBUI_IMPORT_PATTERN.search(text):
            violations.append(str(path.relative_to(REPO_ROOT)))
    assert not violations, f"Main business code must not import OpenWebUI adapter modules: {violations}"


def test_main_business_python_has_no_openwebui_openai_endpoints() -> None:
    violations: list[str] = []
    for path in _iter_python_files():
        text = path.read_text(encoding="utf-8")
        if OPENWEBUI_ENDPOINT_PATTERN.search(text):
            violations.append(str(path.relative_to(REPO_ROOT)))
    assert not violations, f"Main business code must not depend on OpenWebUI /v1 OpenAI endpoints: {violations}"
