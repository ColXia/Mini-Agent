"""Common interface-layer DTOs for API v1 contracts."""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field


class ApiError(BaseModel):
    """Standardized error payload for API v1."""

    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    detail: dict[str, Any] | None = None


TData = TypeVar("TData")


class ApiEnvelope(BaseModel, Generic[TData]):
    """Standardized response envelope for API v1."""

    ok: bool = True
    data: TData | None = None
    error: ApiError | None = None

