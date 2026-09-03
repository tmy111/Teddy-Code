"""Acceptance coverage for provider-native tools and legacy fallback."""

import json
from unittest.mock import patch

from teddycode import SessionStore, TeddyCode, WorkspaceContext
from teddycode.providers import (
    AnthropicCompatibleModelClient,
    ModelResult,
    ModelToolCall,
    OpenAICompatibleModelClient,
)


class NativeScriptedModelClient:
    supports_prompt_cache = False
    supports_native_tools = True
    native_tool_protocol = "openai"

    def __init__(self, results):
        self.results = list(results)
        self.requests = []
        self.last_completion_metadata = {}

    def complete_result(self, prompt, max_new_tokens, **kwargs):
        self.requests.append(
            {"prompt": prompt, "max_new_tokens": max_new_tokens, **kwargs}
        )
        if not self.results:
            raise RuntimeError("native scripted model ran out of results")
        result = self.results.pop(0)
        self.last_completion_metadata = dict(result.metadata)
        return result


class StrictLegacyModelClient:
    supports_prompt_cache = False

    def complete_result(
        self,
        prompt,
        max_new_tokens,
        prompt_cache_key=None,
        prompt_cache_retention=None,
    ):
        del prompt, max_new_tokens, prompt_cache_key, prompt_cache_retention
        return ModelResult(text="<final>legacy complete</final>")


def build_agent(tmp_path, client):
    (tmp_path / "README.md").write_text("demo\n", encoding="utf-8")
    return TeddyCode(
        model_client=client,
        workspace=WorkspaceContext.build(tmp_path),
        session_store=SessionStore(tmp_path / ".teddycode" / "sessions"),
        approval_policy="auto",
    )


def test_engine_executes_native_tool_call_and_accepts_plain_final(tmp_path):
    client = NativeScriptedModelClient(
        [
            ModelResult(
                text="",
                tool_calls=(
                    ModelToolCall(
                        name="read_file",
                        args={"path": "README.md", "start": 1, "end": 1},
                        call_id="call_1",
                    ),
                ),
            ),
            ModelResult(text="Read the file successfully."),
        ]
    )
    agent = build_agent(tmp_path, client)

    assert agent.ask("Read the README") == "Read the file successfully."
    assert client.requests[0]["tools"]
    assert client.requests[0]["tools"][0]["type"] == "function"
    assert client.requests[0]["tools"][0]["strict"] is False
    assert "provider-native tool calling protocol" in client.requests[0]["prompt"]
    assert any(
        item["role"] == "tool" and item["name"] == "read_file"
        for item in agent.session["history"]
    )


def test_native_engine_keeps_xml_response_fallback(tmp_path):
    client = NativeScriptedModelClient(
        [
            ModelResult(
                text='<tool>{"name":"read_file","args":{"path":"README.md","start":1,"end":1}}</tool>'
            ),
            ModelResult(text="<final>fallback complete</final>"),
        ]
    )
    agent = build_agent(tmp_path, client)

    assert agent.ask("Read with fallback") == "fallback complete"
    assert any(item["role"] == "tool" for item in agent.session["history"])


def test_legacy_client_is_not_passed_native_tool_keyword(tmp_path):
    agent = build_agent(tmp_path, StrictLegacyModelClient())

    assert agent.ask("Finish through the legacy protocol") == "legacy complete"
    assert "Valid response examples:" in agent.prefix


def test_openai_client_sends_tools_and_extracts_function_call():
    captured = {}

    class FakeResponse:
        headers = {"Content-Type": "application/json"}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(
                {
                    "output": [
                        {
                            "type": "function_call",
                            "id": "fc_1",
                            "call_id": "call_1",
                            "name": "read_file",
                            "arguments": '{"path":"README.md","start":1,"end":1}',
                        }
                    ]
                }
            ).encode("utf-8")

    def fake_urlopen(request, timeout):
        del timeout
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse()

    client = OpenAICompatibleModelClient(
        model="gpt-test",
        base_url="https://api.openai.com/v1",
        api_key="sk-test",
        temperature=None,
        timeout=30,
    )
    tools = [
        {
            "type": "function",
            "name": "read_file",
            "description": "Read a file.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        }
    ]

    with patch("urllib.request.urlopen", fake_urlopen):
        result = client.complete_result("hello", 42, tools=tools)

    assert captured["body"]["tools"] == tools
    assert result.text == ""
    assert result.tool_calls == (
        ModelToolCall(
            name="read_file",
            args={"path": "README.md", "start": 1, "end": 1},
            call_id="call_1",
        ),
    )
    assert result.metadata["native_tool_call_count"] == 1


def test_anthropic_client_sends_tools_and_extracts_tool_use():
    captured = {}

    class FakeResponse:
        headers = {"Content-Type": "application/json"}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(
                {
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "toolu_1",
                            "name": "read_file",
                            "input": {"path": "README.md", "start": 1, "end": 1},
                        }
                    ]
                }
            ).encode("utf-8")

    def fake_urlopen(request, timeout):
        del timeout
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse()

    client = AnthropicCompatibleModelClient(
        model="claude-test",
        base_url="https://api.anthropic.com/v1",
        api_key="sk-test",
        temperature=None,
        timeout=30,
    )
    tools = [
        {
            "name": "read_file",
            "description": "Read a file.",
            "input_schema": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        }
    ]

    with patch("urllib.request.urlopen", fake_urlopen):
        result = client.complete_result("hello", 42, tools=tools)

    assert captured["body"]["tools"] == tools
    assert result.tool_calls == (
        ModelToolCall(
            name="read_file",
            args={"path": "README.md", "start": 1, "end": 1},
            call_id="toolu_1",
        ),
    )
    assert result.metadata["native_tool_call_count"] == 1


def test_plan_mode_native_specs_follow_active_tool_profile(tmp_path):
    client = NativeScriptedModelClient([])
    agent = build_agent(tmp_path, client)

    assert any(tool["name"] == "run_shell" for tool in agent.native_tools())
    agent.enter_plan_mode("native")

    names = {tool["name"] for tool in agent.native_tools()}
    assert "run_shell" not in names
    assert "write_file" in names
    assert "Runtime mode: plan" in agent.prefix
