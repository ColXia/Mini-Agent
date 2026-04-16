from mini_agent import (
    Agent,
    FunctionCall,
    LLMClient,
    LLMCompletionResult,
    LLMProvider,
    LLMResponse,
    LLMStreamEvent,
    LLMStreamEventType,
    Message,
    ToolCall,
)
from mini_agent.agent_core.engine import Agent as AgentCoreAgent
from mini_agent.llm import LLMClient as CoreLLMClient
from mini_agent.schema import (
    FunctionCall as SchemaFunctionCall,
    LLMCompletionResult as SchemaCompletionResult,
    LLMProvider as SchemaLLMProvider,
    LLMResponse as SchemaLLMResponse,
    LLMStreamEvent as SchemaLLMStreamEvent,
    LLMStreamEventType as SchemaLLMStreamEventType,
    Message as SchemaMessage,
    ToolCall as SchemaToolCall,
)


def test_top_level_package_exports_match_current_runtime_contract() -> None:
    assert Agent is AgentCoreAgent
    assert LLMClient is CoreLLMClient
    assert LLMCompletionResult is SchemaCompletionResult
    assert LLMProvider is SchemaLLMProvider
    assert LLMResponse is SchemaLLMResponse
    assert LLMStreamEvent is SchemaLLMStreamEvent
    assert LLMStreamEventType is SchemaLLMStreamEventType
    assert Message is SchemaMessage
    assert ToolCall is SchemaToolCall
    assert FunctionCall is SchemaFunctionCall
