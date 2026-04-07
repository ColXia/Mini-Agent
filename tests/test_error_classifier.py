"""Tests for provider error classification."""

from mini_agent.model_manager.error_classifier import classify_provider_error


def test_classify_provider_error_timeout_is_retryable():
    classified = classify_provider_error(TimeoutError("read timeout while connecting"))
    assert classified.category == "retryable"
    assert classified.reason == "timeout"
    assert classified.retryable is True
    assert classified.failover_allowed is True


def test_classify_provider_error_auth_failed_is_non_retryable():
    classified = classify_provider_error(RuntimeError("status code: 401 unauthorized"))
    assert classified.category == "non_retryable"
    assert classified.reason == "auth_failed"
    assert classified.retryable is False
    assert classified.failover_allowed is True
    assert classified.status_code == 401


def test_classify_provider_error_cancelled_blocks_failover():
    classified = classify_provider_error(RuntimeError("request cancelled by user"))
    assert classified.category == "cancelled"
    assert classified.reason == "cancelled_by_user"
    assert classified.retryable is False
    assert classified.failover_allowed is False
