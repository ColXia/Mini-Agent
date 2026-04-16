"""Runtime helpers for feature-model bindings such as embedding and OCR."""

from __future__ import annotations

import base64
import html
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

from mini_agent.model_manager.model_registry_service import ModelRegistryService
from mini_agent.tools.docling_parse import DoclingParseResult


_OCR_IMAGE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".bmp",
    ".tif",
    ".tiff",
}


def _is_loopback_url(url: str) -> bool:
    try:
        host = str(urlsplit(url).hostname or "").strip().lower()
    except Exception:
        return False
    return host in {"localhost", "127.0.0.1", "::1"}


def _provider_host_base(api_base: str) -> str:
    normalized = str(api_base or "").strip().rstrip("/")
    lowered = normalized.lower()
    for suffix in ("/v1", "/anthropic"):
        if lowered.endswith(suffix):
            return normalized[: -len(suffix)]
    return normalized


class OpenAICompatibleEmbeddingProvider:
    """Minimal sync embedding provider for OpenAI-compatible endpoints."""

    def __init__(
        self,
        *,
        api_base: str,
        api_key: str,
        model: str,
        headers: dict[str, str] | None = None,
        timeout: int | None = None,
    ) -> None:
        self.api_base = str(api_base or "").strip().rstrip("/")
        self.api_key = str(api_key or "").strip()
        self.model = str(model or "").strip()
        self.headers = dict(headers or {})
        self.timeout = max(5, int(timeout or 60))

    def embed(self, text: str) -> list[float]:
        request_headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            **self.headers,
        }
        with httpx.Client(
            timeout=self.timeout,
            trust_env=not _is_loopback_url(self.api_base),
        ) as client:
            response = client.post(
                f"{self.api_base}/embeddings",
                headers=request_headers,
                json={
                    "model": self.model,
                    "input": str(text or ""),
                },
            )
            response.raise_for_status()
            payload = response.json()
        data = payload.get("data")
        if isinstance(data, list) and data:
            first = data[0]
            if isinstance(first, dict) and isinstance(first.get("embedding"), list):
                return [float(value) for value in first["embedding"]]
        raise ValueError("embedding response missing data[0].embedding")


class OllamaEmbeddingProvider:
    """Minimal sync embedding provider for local Ollama bindings."""

    def __init__(self, *, api_base: str, model: str, timeout: int | None = None) -> None:
        self.host_base = _provider_host_base(api_base)
        self.model = str(model or "").strip()
        self.timeout = max(5, int(timeout or 60))

    def embed(self, text: str) -> list[float]:
        payloads = [
            (f"{self.host_base}/api/embed", {"model": self.model, "input": str(text or "")}),
            (f"{self.host_base}/api/embeddings", {"model": self.model, "prompt": str(text or "")}),
        ]
        errors: list[str] = []
        with httpx.Client(timeout=self.timeout, trust_env=not _is_loopback_url(self.host_base)) as client:
            for endpoint, payload in payloads:
                try:
                    response = client.post(
                        endpoint,
                        headers={"Content-Type": "application/json"},
                        json=payload,
                    )
                    response.raise_for_status()
                    data = response.json()
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{endpoint}: {exc}")
                    continue
                if isinstance(data.get("embedding"), list):
                    return [float(value) for value in data["embedding"]]
                embeddings = data.get("embeddings")
                if isinstance(embeddings, list) and embeddings:
                    first = embeddings[0]
                    if isinstance(first, list):
                        return [float(value) for value in first]
                errors.append(f"{endpoint}: embedding payload missing")
        raise ValueError("; ".join(errors) or "ollama embedding failed")


class OllamaOCRAdapter:
    """Simple image OCR adapter backed by a local Ollama multimodal model."""

    def __init__(self, *, api_base: str, model: str, timeout: int | None = None) -> None:
        self.host_base = _provider_host_base(api_base)
        self.model = str(model or "").strip()
        self.timeout = max(5, int(timeout or 120))

    def __call__(self, source: Path, output_format: str, enable_ocr: bool) -> DoclingParseResult:
        if not enable_ocr:
            raise ValueError("OCR adapter requires enable_ocr=True")
        ext = source.suffix.lower()
        if ext not in _OCR_IMAGE_EXTENSIONS:
            raise ValueError(f"OCR adapter only supports image files, got: {ext or '<none>'}")
        encoded = base64.b64encode(source.read_bytes()).decode("ascii")
        with httpx.Client(timeout=self.timeout, trust_env=not _is_loopback_url(self.host_base)) as client:
            response = client.post(
                f"{self.host_base}/api/generate",
                headers={"Content-Type": "application/json"},
                json={
                    "model": self.model,
                    "prompt": (
                        "Extract all readable text from this image. "
                        "Return plain text only. Do not add commentary."
                    ),
                    "images": [encoded],
                    "stream": False,
                },
            )
            response.raise_for_status()
            payload = response.json()
        text = str(payload.get("response") or "").strip()
        if not text:
            text = str(payload.get("message", {}).get("content") or "").strip()
        metadata = {
            "extension": ext,
            "parser": "ollama_ocr",
            "ocr_model": self.model,
        }
        if output_format == "markdown":
            content = text
        elif output_format == "html":
            content = f"<pre>{html.escape(text)}</pre>"
        else:
            content = json.dumps(
                {
                    "text": text,
                    "source_path": str(source),
                    "extension": ext,
                    "metadata": metadata,
                },
                ensure_ascii=False,
            )
        return DoclingParseResult(
            source_path=str(source),
            output_format=output_format,
            content=content,
            used_docling=True,
            metadata=metadata,
        )


class FeatureModelRuntime:
    """Resolve feature-model bindings into concrete runtime helpers."""

    def __init__(self, *, catalog_path: str | Path | None = None) -> None:
        self._service = ModelRegistryService(
            catalog_path=Path(catalog_path).expanduser().resolve() if catalog_path is not None else None
        )

    def get_embedding_provider(self) -> Any | None:
        binding = self._service.resolve_feature_model_runtime(feature_role="embedding")
        if not isinstance(binding, dict):
            return None
        provider_id = str(binding.get("provider_id") or "")
        api_type = str(binding.get("api_type") or "")
        api_base = str(binding.get("api_base") or "")
        model_id = str(binding.get("model_id") or "")
        if not provider_id or not api_base or not model_id:
            return None
        if provider_id == "ollama" or str(binding.get("provider_family") or "") == "ollama":
            return OllamaEmbeddingProvider(
                api_base=api_base,
                model=model_id,
                timeout=binding.get("timeout"),
            )
        if api_type == "openai":
            return OpenAICompatibleEmbeddingProvider(
                api_base=api_base,
                api_key=str(binding.get("api_key") or ""),
                model=model_id,
                headers=dict(binding.get("headers") or {}),
                timeout=binding.get("timeout"),
            )
        return None

    def get_docling_ocr_adapter(self) -> Any | None:
        binding = self._service.resolve_feature_model_runtime(feature_role="ocr")
        if not isinstance(binding, dict):
            return None
        provider_id = str(binding.get("provider_id") or "")
        api_base = str(binding.get("api_base") or "")
        model_id = str(binding.get("model_id") or "")
        if not provider_id or not api_base or not model_id:
            return None
        if provider_id == "ollama" or str(binding.get("provider_family") or "") == "ollama":
            return OllamaOCRAdapter(
                api_base=api_base,
                model=model_id,
                timeout=binding.get("timeout"),
            )
        return None


__all__ = [
    "FeatureModelRuntime",
    "OllamaEmbeddingProvider",
    "OpenAICompatibleEmbeddingProvider",
    "OllamaOCRAdapter",
]
