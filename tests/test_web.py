import json
import threading
import time

from fastapi.testclient import TestClient

from teddycode import SessionStore, TeddyCode, WorkspaceContext
from teddycode.bootstrap import TeddyCodeConfig
from teddycode.testing import ScriptedModelClient
from teddycode.web.app import create_app
from teddycode.web.session_manager import SessionManager


def sse_events(response):
    return [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]


class RuntimeFactory:
    def __init__(self, outputs):
        self.outputs = list(outputs)

    def __call__(self, config):
        workspace = WorkspaceContext.build(
            config.cwd, repo_root_override=config.repo_root
        )
        store = SessionStore(workspace.repo_root + "/.teddycode/sessions")
        kwargs = {
            "model_client": ScriptedModelClient(self.outputs),
            "workspace": workspace,
            "session_store": store,
            "approval_policy": config.approval,
            "auto_dream": False,
            "final_readiness_mode": "off",
        }
        if config.resume:
            return TeddyCode.from_session(session_id=config.resume, **kwargs)
        session = None
        if config.session_id:
            session = {
                "id": config.session_id,
                "created_at": "2026-01-01T00:00:00+00:00",
                "workspace_root": workspace.repo_root,
                "history": [],
                "memory": {},
            }
        return TeddyCode(session=session, **kwargs)


def build_test_app(tmp_path, factory):
    config = TeddyCodeConfig(
        cwd=str(tmp_path),
        repo_root=str(tmp_path),
        approval="auto",
        auto_dream=False,
    )
    manager = SessionManager(config, agent_factory=factory)
    return create_app(manager=manager), manager


def test_create_and_read_session(tmp_path):
    app, _ = build_test_app(tmp_path, RuntimeFactory(["<final>unused</final>"]))

    with TestClient(app) as client:
        created = client.post("/api/sessions", json={"session_id": "web-test"})
        fetched = client.get("/api/sessions/web-test")
        listed = client.get("/api/sessions")

    assert created.status_code == 200
    assert created.json()["id"] == "web-test"
    assert fetched.status_code == 200
    assert fetched.json()["history"] == []
    assert [row["id"] for row in listed.json()] == ["web-test"]


def test_message_endpoint_streams_engine_events_in_order(tmp_path):
    (tmp_path / "README.md").write_text("demo\n", encoding="utf-8")
    outputs = [
        '<tool>{"name":"read_file","args":{"path":"README.md","start":1,"end":1}}</tool>',
        "<final>Inspection complete.</final>",
    ]
    app, _ = build_test_app(tmp_path, RuntimeFactory(outputs))

    with TestClient(app) as client:
        client.post("/api/sessions", json={"session_id": "stream-test"})
        response = client.post(
            "/api/sessions/stream-test/messages",
            json={"message": "inspect the project"},
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = sse_events(response)
    types = [event["type"] for event in events]
    assert types.index("turn_started") < types.index("tool_call")
    assert types.index("tool_call") < types.index("tool_result")
    assert types.index("tool_result") < types.index("final")
    assert types.index("final") < types.index("turn_finished")
    assert "1: demo" in events[types.index("tool_result")]["content"]


class BlockingEngine:
    def __init__(self, agent):
        self.agent = agent

    def run_turn(self, message):
        yield {"type": "turn_started", "run_id": "run-blocking"}
        self.agent.started.set()
        self.agent.release.wait(timeout=5)
        if self.agent.abort_requested:
            yield {"type": "stop", "run_id": "run-blocking", "content": "Stopped"}
        else:
            yield {"type": "final", "run_id": "run-blocking", "content": "Done"}


class BlockingAgent:
    def __init__(self, config):
        self.session = {
            "id": config.session_id or config.resume or "blocking",
            "created_at": "",
            "workspace_root": config.repo_root,
            "history": [],
        }
        self.model_client = type("Model", (), {"model": "fake-model"})()
        self.started = threading.Event()
        self.release = threading.Event()
        self.abort_requested = False
        self.engine = BlockingEngine(self)
        self.approve = None
        self.ask_user_callback = None

    def abort_current_turn(self):
        self.abort_requested = True
        self.release.set()


def _start_message(client, path, result):
    result.append(client.post(path, json={"message": "work"}))


def test_same_session_rejects_concurrent_turn(tmp_path):
    app, manager = build_test_app(tmp_path, BlockingAgent)
    manager.create_session(session_id="blocking")
    first_result = []

    with TestClient(app) as first_client, TestClient(app) as second_client:
        thread = threading.Thread(
            target=_start_message,
            args=(first_client, "/api/sessions/blocking/messages", first_result),
        )
        thread.start()
        assert manager.get_session("blocking").agent.started.wait(timeout=2)
        second = second_client.post(
            "/api/sessions/blocking/messages", json={"message": "overlap"}
        )
        manager.get_session("blocking").agent.release.set()
        thread.join(timeout=3)

    assert second.status_code == 409
    assert first_result[0].status_code == 200


def test_abort_stops_active_turn_and_streams_stop(tmp_path):
    app, manager = build_test_app(tmp_path, BlockingAgent)
    manager.create_session(session_id="abort-test")
    result = []

    with TestClient(app) as stream_client, TestClient(app) as action_client:
        thread = threading.Thread(
            target=_start_message,
            args=(stream_client, "/api/sessions/abort-test/messages", result),
        )
        thread.start()
        assert manager.get_session("abort-test").agent.started.wait(timeout=2)
        aborted = action_client.post("/api/sessions/abort-test/abort")
        thread.join(timeout=3)

    assert aborted.status_code == 200
    assert aborted.json() == {"aborted": True}
    assert [event["type"] for event in sse_events(result[0])] == [
        "turn_started",
        "stop",
    ]


class ApprovalEngine:
    def __init__(self, agent):
        self.agent = agent

    def run_turn(self, message):
        yield {"type": "turn_started", "run_id": "run-approval"}
        allowed = self.agent.approve("write_file", {"path": "answer.txt"})
        yield {
            "type": "final",
            "run_id": "run-approval",
            "content": "allowed" if allowed else "denied",
        }


class ApprovalAgent(BlockingAgent):
    def __init__(self, config):
        super().__init__(config)
        self.engine = ApprovalEngine(self)


def test_approval_request_round_trips_through_api(tmp_path):
    app, manager = build_test_app(tmp_path, ApprovalAgent)
    manager.create_session(session_id="approval-test", approval="ask")
    result = []

    with TestClient(app) as stream_client, TestClient(app) as action_client:
        thread = threading.Thread(
            target=_start_message,
            args=(stream_client, "/api/sessions/approval-test/messages", result),
        )
        thread.start()
        session = manager.get_session("approval-test")
        deadline = time.monotonic() + 2
        while not session.pending and time.monotonic() < deadline:
            time.sleep(0.01)
        request_id = next(iter(session.pending))
        decision = action_client.post(
            f"/api/sessions/approval-test/approvals/{request_id}",
            json={"decision": "allow"},
        )
        thread.join(timeout=3)

    assert decision.status_code == 200
    events = sse_events(result[0])
    assert [event["type"] for event in events] == [
        "turn_started",
        "approval_required",
        "final",
    ]
    assert events[-1]["content"] == "allowed"


class QuestionEngine:
    def __init__(self, agent):
        self.agent = agent

    def run_turn(self, message):
        yield {"type": "turn_started", "run_id": "run-question"}
        answer = self.agent.ask_user_callback("Target?", ["staging", "production"])
        yield {"type": "final", "run_id": "run-question", "content": answer}


class QuestionAgent(BlockingAgent):
    def __init__(self, config):
        super().__init__(config)
        self.engine = QuestionEngine(self)


def test_ask_user_question_round_trips_through_api(tmp_path):
    app, manager = build_test_app(tmp_path, QuestionAgent)
    manager.create_session(session_id="question-test")
    result = []

    with TestClient(app) as stream_client, TestClient(app) as action_client:
        thread = threading.Thread(
            target=_start_message,
            args=(stream_client, "/api/sessions/question-test/messages", result),
        )
        thread.start()
        session = manager.get_session("question-test")
        deadline = time.monotonic() + 2
        while not session.pending and time.monotonic() < deadline:
            time.sleep(0.01)
        request_id = next(iter(session.pending))
        answer = action_client.post(
            f"/api/sessions/question-test/questions/{request_id}",
            json={"answer": "production"},
        )
        thread.join(timeout=3)

    assert answer.status_code == 200
    events = sse_events(result[0])
    assert [event["type"] for event in events] == [
        "turn_started",
        "question_required",
        "final",
    ]
    assert events[-1]["content"] == "production"


def test_workspace_file_endpoint_blocks_path_traversal(tmp_path):
    (tmp_path / "inside.txt").write_text("safe", encoding="utf-8")
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("private", encoding="utf-8")
    app, _ = build_test_app(tmp_path, RuntimeFactory(["<final>unused</final>"]))

    with TestClient(app) as client:
        safe = client.get("/api/workspace/file", params={"path": "inside.txt"})
        escaped = client.get("/api/workspace/file", params={"path": "../outside.txt"})

    assert safe.status_code == 200
    assert safe.text == "safe"
    assert escaped.status_code == 400
