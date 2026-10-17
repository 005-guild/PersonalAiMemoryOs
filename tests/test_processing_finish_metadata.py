"""Provider metadata is preserved only as known finish states and numeric counters."""

import pytest

from app.agents.errors import AIError
from app.agents.protocols import parse_response


@pytest.mark.parametrize("protocol,payload,finish", [
    ("openai_chat", {"choices": [{"finish_reason": "length", "message": {"content": "secret raw reply"}}],
                     "usage": {"prompt_tokens": 3, "completion_tokens": 7, "private": "credential"}}, "length"),
    ("openai_responses", {"status": "incomplete", "usage": {"input_tokens": 3, "output_tokens": 7}}, "incomplete"),
    ("anthropic_messages", {"stop_reason": "max_tokens", "usage": {"input_tokens": 3, "output_tokens": 7}}, "max_tokens"),
    ("gemini_generate_content", {"candidates": [{"finishReason": "MAX_TOKENS"}],
                                 "usageMetadata": {"promptTokenCount": 3, "candidatesTokenCount": 7}}, "MAX_TOKENS"),
])
def test_truncation_metadata_has_safe_usage(protocol, payload, finish):
    with pytest.raises(AIError) as error:
        parse_response(protocol, payload)
    assert error.value.code == "model_output_truncated"
    assert error.value.finish_reason == finish
    assert error.value.usage == {"input_tokens": 3, "output_tokens": 7, "total_tokens": 10}
    assert str(error.value) == "model_output_truncated"


def test_untrusted_finish_value_is_not_exposed():
    with pytest.raises(AIError) as error:
        parse_response("openai_chat", {"choices": [{"finish_reason": "private-credential-value"}], "usage": {"prompt_tokens": -1}})
    assert error.value.finish_reason is None
    assert "private" not in str(error.value)
