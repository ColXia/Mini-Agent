import mini_agent


def test_top_level_package_is_marker_only_and_drops_legacy_sdk_exports() -> None:
    assert mini_agent.__all__ == []

    for name in (
        "__version__",
        "Agent",
        "LLMClient",
        "LLMCompletionResult",
        "LLMProvider",
        "LLMResponse",
        "LLMStreamEvent",
        "LLMStreamEventType",
        "Message",
        "ToolCall",
        "FunctionCall",
    ):
        assert not hasattr(mini_agent, name), f"{name} should not remain on the package root"
