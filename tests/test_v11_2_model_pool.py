"""Tests for v11.2 model pool service."""

from __future__ import annotations

import pytest
from datetime import datetime, timezone

from mini_agent.model_manager.model_pool_contracts import (
    CapabilityTruth,
    ModelDescriptor,
    ModelKind,
    ProviderEntry,
    ProviderSource,
    ProtocolFamily,
)
from mini_agent.model_manager.model_pool import (
    BreakerStatus,
    HealthStatus,
    ModelPool,
    ModelPoolSnapshot,
    build_model_pool_from_preset,
    clear_shared_model_pool,
    shared_model_pool,
)


class TestModelPool:
    """Tests for ModelPool service."""

    def test_model_pool_register_provider(self) -> None:
        pool = ModelPool()
        entry = ProviderEntry(
            provider_id="test-provider",
            provider_source=ProviderSource.CUSTOM,
            protocol_family=ProtocolFamily.OPENAI,
            api_base="https://api.test.com/v1",
            provider_name="Test Provider",
        )
        pool.register_provider(entry)
        assert pool.get_provider("test-provider") is not None
        assert len(pool.list_providers()) == 1

    def test_model_pool_register_model(self) -> None:
        pool = ModelPool()
        pool.register_provider(ProviderEntry(
            provider_id="test-provider",
            provider_source=ProviderSource.CUSTOM,
            protocol_family=ProtocolFamily.OPENAI,
            api_base="https://api.test.com/v1",
            provider_name="Test Provider",
        ))
        descriptor = ModelDescriptor(
            provider_id="test-provider",
            model_id="test-model",
            display_name="Test Model",
            context_window=8000,
        )
        pool.register_model(descriptor)
        assert pool.get_model("test-model") is not None
        assert len(pool.list_models()) == 1

    def test_model_pool_unregister_provider(self) -> None:
        pool = ModelPool()
        pool.register_provider(ProviderEntry(
            provider_id="test-provider",
            provider_source=ProviderSource.CUSTOM,
            protocol_family=ProtocolFamily.OPENAI,
            api_base="https://api.test.com/v1",
            provider_name="Test Provider",
        ))
        pool.register_model(ModelDescriptor(
            provider_id="test-provider",
            model_id="test-model",
            display_name="Test Model",
        ))
        pool.unregister_provider("test-provider")
        assert pool.get_provider("test-provider") is None
        assert pool.get_model("test-model") is None

    def test_model_pool_health_status(self) -> None:
        pool = ModelPool()
        pool.register_provider(ProviderEntry(
            provider_id="test-provider",
            provider_source=ProviderSource.CUSTOM,
            protocol_family=ProtocolFamily.OPENAI,
            api_base="https://api.test.com/v1",
            provider_name="Test Provider",
        ))
        status = HealthStatus(
            provider_id="test-provider",
            is_healthy=True,
            latency_ms=100,
        )
        pool.update_health_status(status)
        assert pool.get_health_status("test-provider").is_healthy is True

    def test_model_pool_breaker_status(self) -> None:
        pool = ModelPool()
        pool.register_provider(ProviderEntry(
            provider_id="test-provider",
            provider_source=ProviderSource.CUSTOM,
            protocol_family=ProtocolFamily.OPENAI,
            api_base="https://api.test.com/v1",
            provider_name="Test Provider",
        ))
        status = BreakerStatus(
            provider_id="test-provider",
            is_open=True,
            failure_count=3,
        )
        pool.update_breaker_status(status)
        assert pool.get_breaker_status("test-provider").is_open is True

    def test_model_pool_failover_candidates(self) -> None:
        pool = ModelPool()
        pool.set_failover_candidates("provider-a", ("provider-b", "provider-c"))
        assert pool.get_failover_candidates("provider-a") == ("provider-b", "provider-c")

    def test_model_pool_capability_profile(self) -> None:
        pool = ModelPool()
        pool.register_provider(ProviderEntry(
            provider_id="test-provider",
            provider_source=ProviderSource.CUSTOM,
            protocol_family=ProtocolFamily.OPENAI,
            api_base="https://api.test.com/v1",
            provider_name="Test Provider",
        ))
        pool.register_model(ModelDescriptor(
            provider_id="test-provider",
            model_id="test-model",
            display_name="Test Model",
            supports_tools_truth=CapabilityTruth.SUPPORTED,
        ))
        profile = pool.get_capability_profile("test-model")
        assert profile is not None
        assert profile.supports_tools is True

    def test_model_pool_create_snapshot(self) -> None:
        pool = ModelPool()
        pool.register_provider(ProviderEntry(
            provider_id="test-provider",
            provider_source=ProviderSource.CUSTOM,
            protocol_family=ProtocolFamily.OPENAI,
            api_base="https://api.test.com/v1",
            provider_name="Test Provider",
            enabled=True,
        ))
        pool.register_model(ModelDescriptor(
            provider_id="test-provider",
            model_id="test-model",
            display_name="Test Model",
        ))
        snapshot = pool.create_snapshot()
        assert snapshot.provider_count == 1
        assert snapshot.model_count == 1
        assert snapshot.snapshot_timestamp is not None


class TestModelPoolSnapshot:
    """Tests for ModelPoolSnapshot."""

    def test_snapshot_provider_count(self) -> None:
        snapshot = ModelPoolSnapshot(
            snapshot_id="test-snapshot",
            available_providers=(
                ProviderEntry(
                    provider_id="provider-a",
                    provider_source=ProviderSource.CUSTOM,
                    protocol_family=ProtocolFamily.OPENAI,
                    api_base="https://a.api.com",
                    provider_name="Provider A",
                ),
                ProviderEntry(
                    provider_id="provider-b",
                    provider_source=ProviderSource.CUSTOM,
                    protocol_family=ProtocolFamily.OPENAI,
                    api_base="https://b.api.com",
                    provider_name="Provider B",
                ),
            ),
            available_models=(),
        )
        assert snapshot.provider_count == 2

    def test_snapshot_get_provider(self) -> None:
        provider = ProviderEntry(
            provider_id="test-provider",
            provider_source=ProviderSource.CUSTOM,
            protocol_family=ProtocolFamily.OPENAI,
            api_base="https://api.test.com",
            provider_name="Test",
        )
        snapshot = ModelPoolSnapshot(
            snapshot_id="test-snapshot",
            available_providers=(provider,),
            available_models=(),
        )
        assert snapshot.get_provider("test-provider") is not None
        assert snapshot.get_provider("nonexistent") is None

    def test_snapshot_get_model(self) -> None:
        model = ModelDescriptor(
            provider_id="test-provider",
            model_id="test-model",
            display_name="Test Model",
        )
        snapshot = ModelPoolSnapshot(
            snapshot_id="test-snapshot",
            available_providers=(),
            available_models=(model,),
        )
        assert snapshot.get_model("test-model") is not None
        assert snapshot.get_model("test-model", "test-provider") is not None
        assert snapshot.get_model("test-model", "wrong-provider") is None

    def test_snapshot_list_models_by_provider(self) -> None:
        model_a = ModelDescriptor(
            provider_id="provider-a",
            model_id="model-a",
            display_name="Model A",
        )
        model_b = ModelDescriptor(
            provider_id="provider-b",
            model_id="model-b",
            display_name="Model B",
        )
        snapshot = ModelPoolSnapshot(
            snapshot_id="test-snapshot",
            available_providers=(),
            available_models=(model_a, model_b),
        )
        provider_a_models = snapshot.list_models_by_provider("provider-a")
        assert len(provider_a_models) == 1
        assert provider_a_models[0].model_id == "model-a"

    def test_snapshot_list_models_with_tools(self) -> None:
        model_with_tools = ModelDescriptor(
            provider_id="provider",
            model_id="model-tools",
            display_name="Model with Tools",
            supports_tools_truth=CapabilityTruth.SUPPORTED,
        )
        model_without_tools = ModelDescriptor(
            provider_id="provider",
            model_id="model-no-tools",
            display_name="Model without Tools",
            supports_tools_truth=CapabilityTruth.UNSUPPORTED,
        )
        snapshot = ModelPoolSnapshot(
            snapshot_id="test-snapshot",
            available_providers=(),
            available_models=(model_with_tools, model_without_tools),
        )
        tools_models = snapshot.list_models_with_tools()
        assert len(tools_models) == 1
        assert tools_models[0].model_id == "model-tools"

    def test_snapshot_healthy_providers(self) -> None:
        provider_a = ProviderEntry(
            provider_id="provider-a",
            provider_source=ProviderSource.CUSTOM,
            protocol_family=ProtocolFamily.OPENAI,
            api_base="https://a.api.com",
            provider_name="Provider A",
        )
        provider_b = ProviderEntry(
            provider_id="provider-b",
            provider_source=ProviderSource.CUSTOM,
            protocol_family=ProtocolFamily.OPENAI,
            api_base="https://b.api.com",
            provider_name="Provider B",
        )
        health_a = HealthStatus(provider_id="provider-a", is_healthy=True)
        health_b = HealthStatus(provider_id="provider-b", is_healthy=False)
        snapshot = ModelPoolSnapshot(
            snapshot_id="test-snapshot",
            available_providers=(provider_a, provider_b),
            available_models=(),
            health_status=(health_a, health_b),
        )
        healthy = snapshot.healthy_provider_ids
        assert len(healthy) == 1
        assert healthy[0] == "provider-a"


class TestSharedModelPool:
    """Tests for shared model pool."""

    def test_shared_model_pool_singleton(self) -> None:
        clear_shared_model_pool()
        pool1 = shared_model_pool()
        pool2 = shared_model_pool()
        assert pool1 is pool2

    def test_clear_shared_model_pool(self) -> None:
        pool = shared_model_pool()
        pool.register_provider(ProviderEntry(
            provider_id="test",
            provider_source=ProviderSource.CUSTOM,
            protocol_family=ProtocolFamily.OPENAI,
            api_base="https://test.com",
            provider_name="Test",
        ))
        clear_shared_model_pool()
        pool2 = shared_model_pool()
        assert pool is not pool2
