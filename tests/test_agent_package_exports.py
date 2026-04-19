import mini_agent


def test_top_level_package_drops_legacy_sdk_exports() -> None:
    assert mini_agent.__all__ == ["__version__"]
    assert hasattr(mini_agent, "__version__")

    for name in (
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
