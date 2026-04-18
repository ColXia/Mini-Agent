from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SURFACE_ROOTS = (
    REPO_ROOT / "src" / "mini_agent" / "desktop",
    REPO_ROOT / "src" / "mini_agent" / "tui",
)
FORBIDDEN_SNIPPETS = (
    ".model_dump(",
    "to_transport().model_dump(",
)


def _violation_lines(path: Path) -> list[str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        lines = path.read_text(encoding="utf-8-sig").splitlines()

    violations: list[str] = []
    for line_number, line in enumerate(lines, start=1):
        if any(snippet in line for snippet in FORBIDDEN_SNIPPETS):
            violations.append(f"{path.relative_to(REPO_ROOT)}:{line_number}: {line.strip()}")
    return violations


def test_surface_layers_do_not_serialize_transport_dtos_directly() -> None:
    violations: list[str] = []
    for root in SURFACE_ROOTS:
        for path in sorted(root.rglob("*.py")):
            violations.extend(_violation_lines(path))

    assert violations == [], (
        "Surface files must use the shared payload adapter instead of direct DTO serialization:\n"
        + "\n".join(violations)
    )
