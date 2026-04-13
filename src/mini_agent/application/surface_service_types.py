"""Shared callable types for surface-level application services."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from fastapi import HTTPException

ResolveWorkspaceDirFn = Callable[[str | None], Path]
ToUtcIsoFn = Callable[[datetime], str]
SseEventFn = Callable[[str, dict[str, Any]], str]
FormatBootstrapErrorFn = Callable[[Exception], HTTPException]

__all__ = [
    "FormatBootstrapErrorFn",
    "ResolveWorkspaceDirFn",
    "SseEventFn",
    "ToUtcIsoFn",
]
