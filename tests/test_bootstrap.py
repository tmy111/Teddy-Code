from teddycode.bootstrap import TeddyCodeConfig, create_agent
from teddycode.providers.runtime import ProviderClientClasses


class FakeModelClient:
    def __init__(self, **kwargs):
        self.model = kwargs["model"]
        self.base_url = kwargs["base_url"]
        self.supports_prompt_cache = False

    def complete(self, prompt, max_new_tokens, **kwargs):
        return "<final>ok</final>"


def test_create_agent_builds_runtime_without_cli_namespace(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    agent = create_agent(
        TeddyCodeConfig(cwd=str(tmp_path), approval="auto"),
        client_classes=ProviderClientClasses(
            openai=FakeModelClient,
            anthropic=FakeModelClient,
        ),
    )

    assert agent.workspace.repo_root == str(tmp_path.resolve())
    assert agent.approval_policy == "auto"
    assert agent.ask("hello") == "ok"


def test_create_agent_resumes_shared_session_store(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    clients = ProviderClientClasses(openai=FakeModelClient, anthropic=FakeModelClient)
    first = create_agent(
        TeddyCodeConfig(cwd=str(tmp_path), session_id="web-shared"),
        client_classes=clients,
    )
    first.record({"role": "user", "content": "remember me"})

    resumed = create_agent(
        TeddyCodeConfig(cwd=str(tmp_path), resume="web-shared"),
        client_classes=clients,
    )

    assert resumed.session["id"] == "web-shared"
    assert resumed.session["history"][-1]["content"] == "remember me"
