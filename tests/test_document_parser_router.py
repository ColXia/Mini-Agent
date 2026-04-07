"""Tests for document parser subprogram router."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from subprograms.document_parser.gateway.router import router


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_document_parser_router_health_and_formats():
    client = _client()

    health = client.get("/api/document-parser/health")
    formats = client.get("/api/document-parser/formats")

    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert formats.status_code == 200
    assert ".pdf" in formats.json()["input_extensions"]
    assert "markdown" in formats.json()["output_formats"]


def test_document_parser_router_parse_and_batch(tmp_path):
    source_ok = tmp_path / "sample.txt"
    source_ok.write_text("hello parser", encoding="utf-8")
    source_missing = tmp_path / "missing.txt"

    client = _client()
    single = client.post(
        "/api/document-parser/parse",
        json={
            "path": str(source_ok),
            "output_format": "markdown",
            "enable_ocr": False,
        },
    )
    batch = client.post(
        "/api/document-parser/parse/batch",
        json={
            "paths": [str(source_ok), str(source_missing)],
            "output_format": "markdown",
            "enable_ocr": False,
        },
    )

    assert single.status_code == 200
    assert single.json()["status"] == "ok"
    assert "hello parser" in single.json()["content"]

    assert batch.status_code == 200
    payload = batch.json()
    assert payload["total"] == 2
    assert payload["succeeded"] == 1
    assert payload["failed"] == 1
