from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"


def test_compatibility_reexport_modules_follow_lazy_wrapper_shape() -> None:
    violations: list[str] = []
    for path in sorted(SRC_ROOT.rglob("*.py")):
        try:
            text = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            text = path.read_text(encoding="utf-8")
        if "Compatibility re-export for" not in text:
            continue

        missing: list[str] = []
        for marker in ("_COMPAT_EXPORTS", "def __getattr__", "def __dir__"):
            if marker not in text:
                missing.append(marker)
        if missing:
            violations.append(
                f"{path.relative_to(REPO_ROOT)}: missing {', '.join(missing)}"
            )

    assert violations == [], (
        "Compatibility re-export modules must use the lazy wrapper shape:\n"
        + "\n".join(violations)
    )
