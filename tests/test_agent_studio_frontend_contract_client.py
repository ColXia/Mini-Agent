from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _resolve_api_dir() -> Path:
    src_layout = REPO_ROOT / "src" / "apps" / "agent_studio" / "src" / "api"
    legacy_layout = REPO_ROOT / "apps" / "agent_studio" / "src" / "api"
    if src_layout.exists():
        return src_layout
    return legacy_layout


API_DIR = _resolve_api_dir()


def _read_api_sources() -> str:
    chunks: list[str] = []
    for path in sorted(API_DIR.glob("*.ts")):
        chunks.append(path.read_text(encoding="utf-8"))
    return "\n".join(chunks)


def test_frontend_api_client_uses_v1_namespace_only() -> None:
    text = _read_api_sources()
    assert "/api/studio" not in text
    assert "/api/chat" not in text
    assert "/api/sessions" not in text
    assert "/api/health" not in text
    assert "/api/novel/" not in text
    assert "/api/v1/" in text
    # OpenWebUI is an optional adapter, not Studio's primary contract surface.
    assert "/v1/chat/completions" not in text
    assert "/v1/models" not in text
    assert "open_webui" not in text.lower()


def test_frontend_channel_client_targets_v1_contract() -> None:
    path = API_DIR / "agent.ts"
    text = path.read_text(encoding="utf-8")
    assert "/api/v1/channel/message" in text


def test_frontend_api_layer_is_split_by_domain_module() -> None:
    expected = {
        "client.ts",
        "agent.ts",
        "knowledge.ts",
        "novel.ts",
        "ops.ts",
        "index.ts",
    }
    existing = {item.name for item in API_DIR.glob("*.ts")}
    assert expected.issubset(existing)


def test_frontend_ops_client_targets_runtime_diagnostics_contract() -> None:
    path = API_DIR / "ops.ts"
    text = path.read_text(encoding="utf-8")
    assert "/api/v1/ops/diagnostics/runtime" in text
