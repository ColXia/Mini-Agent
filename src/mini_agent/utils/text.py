"""Text utility functions for Mini-Agent."""

from __future__ import annotations

from typing import Any


def safe_text(value: Any) -> str:
    """Safely convert any value to a normalized text string.

    Strips whitespace and returns empty string for None/empty values.

    Args:
        value: Any value to convert to text.

    Returns:
        Normalized text string with whitespace collapsed.
    """
    return " ".join(str(value or "").split())


__all__ = ["safe_text"]
