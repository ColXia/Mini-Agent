"""Tests for mini_agent.retry module."""

from __future__ import annotations

import asyncio

import pytest

from mini_agent.retry import RetryConfig, RetryExhaustedError, async_retry


class TestRetryConfig:
    def test_default_values(self) -> None:
        cfg = RetryConfig()
        assert cfg.enabled is True
        assert cfg.max_retries == 3
        assert cfg.initial_delay == 1.0
        assert cfg.max_delay == 60.0
        assert cfg.exponential_base == 2.0
        assert cfg.retryable_exceptions == (Exception,)

    def test_calculate_delay_exponential(self) -> None:
        cfg = RetryConfig(initial_delay=1.0, exponential_base=2.0, max_delay=100.0)
        assert cfg.calculate_delay(0) == 1.0
        assert cfg.calculate_delay(1) == 2.0
        assert cfg.calculate_delay(2) == 4.0
        assert cfg.calculate_delay(3) == 8.0

    def test_calculate_delay_capped_by_max(self) -> None:
        cfg = RetryConfig(initial_delay=10.0, exponential_base=2.0, max_delay=15.0)
        assert cfg.calculate_delay(0) == 10.0
        assert cfg.calculate_delay(1) == 15.0
        assert cfg.calculate_delay(5) == 15.0

    def test_custom_retryable_exceptions(self) -> None:
        cfg = RetryConfig(retryable_exceptions=(ValueError, TypeError))
        assert cfg.retryable_exceptions == (ValueError, TypeError)


class TestRetryExhaustedError:
    def test_attributes(self) -> None:
        original = ValueError("boom")
        err = RetryExhaustedError(original, 4)
        assert err.last_exception is original
        assert err.attempts == 4
        assert "4 attempts" in str(err)
        assert "boom" in str(err)


class TestAsyncRetry:
    @pytest.mark.asyncio
    async def test_success_on_first_try(self) -> None:
        call_count = 0

        @async_retry(RetryConfig(max_retries=3, initial_delay=0))
        async def succeed():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = await succeed()
        assert result == "ok"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_success_after_retries(self) -> None:
        call_count = 0

        @async_retry(RetryConfig(max_retries=3, initial_delay=0))
        async def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("not yet")
            return "ok"

        result = await flaky()
        assert result == "ok"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_exhausted_raises(self) -> None:
        @async_retry(RetryConfig(max_retries=2, initial_delay=0))
        async def always_fail():
            raise ValueError("always")

        with pytest.raises(RetryExhaustedError) as exc_info:
            await always_fail()
        assert exc_info.value.attempts == 3
        assert isinstance(exc_info.value.last_exception, ValueError)

    @pytest.mark.asyncio
    async def test_non_retryable_exception_propagates(self) -> None:
        @async_retry(RetryConfig(max_retries=3, initial_delay=0, retryable_exceptions=(ValueError,)))
        async def raise_type_error():
            raise TypeError("wrong type")

        with pytest.raises(TypeError, match="wrong type"):
            await raise_type_error()

    @pytest.mark.asyncio
    async def test_on_retry_callback(self) -> None:
        callback_calls: list[tuple[str, int]] = []

        def on_retry(exc: Exception, attempt: int) -> None:
            callback_calls.append((str(exc), attempt))

        call_count = 0

        @async_retry(RetryConfig(max_retries=3, initial_delay=0), on_retry=on_retry)
        async def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError(f"fail-{call_count}")
            return "ok"

        await flaky()
        assert len(callback_calls) == 2
        assert callback_calls[0] == ("fail-1", 1)
        assert callback_calls[1] == ("fail-2", 2)

    @pytest.mark.asyncio
    async def test_disabled_retry_still_executes_once(self) -> None:
        call_count = 0

        @async_retry(RetryConfig(enabled=False, max_retries=3, initial_delay=0))
        async def succeed():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = await succeed()
        assert result == "ok"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_default_config_used_when_none(self) -> None:
        call_count = 0

        @async_retry()
        async def succeed():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = await succeed()
        assert result == "ok"
        assert call_count == 1
