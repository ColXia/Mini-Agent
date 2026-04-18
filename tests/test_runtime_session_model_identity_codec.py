from __future__ import annotations

from mini_agent.runtime.session_model_identity_codec import RuntimeSessionModelIdentityCodec
from tests.runtime_contract_fixtures import (
    RuntimeContractAgentStub,
    runtime_projection_stub,
    runtime_session_stub,
)


def test_model_identity_codec_routes_runtime_route_to_canonical_identity() -> None:
    codec = RuntimeSessionModelIdentityCodec()

    preset_agent = RuntimeContractAgentStub(
        model="gpt-5.4",
        provider_source="preset",
        provider_id="openai",
    )
    custom_agent = RuntimeContractAgentStub(
        model="astron-code-latest",
        provider_source="custom",
        provider_id="maas",
    )
    bootstrap_agent = RuntimeContractAgentStub(
        model="m2",
        runtime_provider_id="bootstrap-config",
    )

    assert codec.route_model_identity(preset_agent) == ("preset", "openai", "gpt-5.4")
    assert codec.route_model_identity(custom_agent) == ("custom", "maas", "astron-code-latest")
    assert codec.route_model_identity(bootstrap_agent) == ("bootstrap", "bootstrap-config", "m2")


def test_model_identity_codec_reads_and_updates_selected_and_pending_identity() -> None:
    codec = RuntimeSessionModelIdentityCodec()
    session = runtime_session_stub(
        projection=runtime_projection_stub(
            selected_model_source="preset",
            selected_provider_id="openai",
            selected_model_id="gpt-5.4",
            pending_model_source=None,
            pending_provider_id=None,
            pending_model_id=None,
        ),
        agent=RuntimeContractAgentStub(
            model="gpt-5.4",
            provider_source="preset",
            provider_id="openai",
        ),
    )

    assert codec.selected_model_identity(session) == ("preset", "openai", "gpt-5.4")
    assert codec.pending_model_identity(session) is None

    codec.set_pending_model_identity(session, ("custom", "maas", "astron-code-latest"))
    assert codec.pending_model_identity(session) == ("custom", "maas", "astron-code-latest")

    codec.set_selected_model_identity(session, None)
    assert codec.selected_model_identity(session) == ("preset", "openai", "gpt-5.4")


def test_model_identity_codec_prefers_runtime_route_over_projection_identity() -> None:
    codec = RuntimeSessionModelIdentityCodec()
    session = runtime_session_stub(
        projection=runtime_projection_stub(
            selected_model_source="preset",
            selected_provider_id="openai",
            selected_model_id="gpt-5.4",
        ),
        agent=RuntimeContractAgentStub(
            model="astron-code-latest",
            provider_source="custom",
            provider_id="maas",
        ),
    )

    assert codec.selected_model_identity(session) == ("custom", "maas", "astron-code-latest")


def test_model_identity_codec_projection_helpers_normalize_shape_and_route_payloads() -> None:
    codec = RuntimeSessionModelIdentityCodec()
    projection = runtime_projection_stub(
        selected_model_source=" PRESET ",
        selected_provider_id="openai",
        selected_model_id="gpt-5.4",
        pending_model_source=" CUSTOM ",
        pending_provider_id="maas",
        pending_model_id="astron-code-latest",
    )

    assert codec.selected_identity_from_projection(projection) == ("preset", "openai", "gpt-5.4")
    assert codec.pending_identity_from_projection(projection) == ("custom", "maas", "astron-code-latest")

    codec.set_selected_identity_on_projection(projection, (" PRESET ", "openai", "gpt-5.3"))
    codec.set_pending_identity_on_projection(projection, (" CUSTOM ", "maas", "astron-code-next"))

    assert projection.selected_model_source == "preset"
    assert projection.selected_model_id == "gpt-5.3"
    assert projection.pending_model_source == "custom"
    assert projection.pending_model_id == "astron-code-next"
    assert codec.route_model_identity_from_route(
        RuntimeContractAgentStub(
            model="gpt-5.4",
            provider_source="preset",
            provider_id="openai",
        ).runtime_route
    ) == ("preset", "openai", "gpt-5.4")
