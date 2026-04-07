"""Tests for knowledge-base settings parsing."""

from __future__ import annotations

from subprograms.knowledge_base.config import KnowledgeBaseSettings


def test_knowledge_base_settings_from_env_defaults(monkeypatch):
    monkeypatch.delenv("MINI_AGENT_RAG_STORE_PATH", raising=False)
    monkeypatch.delenv("MINI_AGENT_RAG_TOP_K_DEFAULT", raising=False)
    monkeypatch.delenv("MINI_AGENT_RAG_TOP_K_MAX", raising=False)

    settings = KnowledgeBaseSettings.from_env()

    assert str(settings.store_path).endswith("workspace\\rag\\light_hybrid_store.json")
    assert settings.query_top_k_default == 5
    assert settings.query_top_k_max == 20


def test_knowledge_base_settings_validates_overlap(monkeypatch):
    monkeypatch.setenv("MINI_AGENT_RAG_CHUNK_SIZE", "100")
    monkeypatch.setenv("MINI_AGENT_RAG_CHUNK_OVERLAP", "100")

    try:
        KnowledgeBaseSettings.from_env()
    except ValueError as exc:
        assert "CHUNK_OVERLAP" in str(exc)
    else:
        raise AssertionError("expected ValueError for overlap >= chunk size")
