import json

import pytest

from teddycode.core import run_store as run_store_module
from teddycode.core.run_store import RunStore
from teddycode.core.task_state import STOP_REASON_FINAL_ANSWER_RETURNED, TaskState


def test_run_store_creates_run_directory_and_state_file(tmp_path):
    store = RunStore(tmp_path / ".teddycode" / "runs")
    state = TaskState.create(run_id="run_001", task_id="task_001", user_request="Inspect the repo.")

    run_dir = store.start_run(state)

    assert run_dir == store.run_dir(state.run_id)
    assert run_dir.exists()
    persisted = json.loads((run_dir / "task_state.json").read_text(encoding="utf-8"))
    assert persisted["task_id"] == "task_001"
    assert persisted["run_id"] == "run_001"
    assert persisted["user_request"] == "Inspect the repo."


def test_run_store_appends_trace_jsonl(tmp_path):
    store = RunStore(tmp_path / ".teddycode" / "runs")
    state = TaskState.create(run_id="run_002", task_id="task_002", user_request="Trace the run.")
    store.start_run(state)

    store.append_trace(state, {"event": "run_started", "created_at": "2026-04-07T00:00:00+00:00"})
    store.append_trace(
        state.run_id,
        {
            "event": "prompt_built",
            "created_at": "2026-04-07T00:00:01+00:00",
            "prompt_metadata": {"prompt_chars": 128, "secret_env_count": 1},
        },
    )
    store.append_trace(state.run_id, {"event": "run_finished", "created_at": "2026-04-07T00:00:02+00:00"})

    lines = (store.trace_path(state.run_id)).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    assert json.loads(lines[0])["event"] == "run_started"
    assert json.loads(lines[1])["event"] == "prompt_built"
    assert json.loads(lines[2])["event"] == "run_finished"


def test_run_store_writes_report_json(tmp_path):
    store = RunStore(tmp_path / ".teddycode" / "runs")
    state = TaskState.create(run_id="run_003", task_id="task_003", user_request="Report the run.")
    store.start_run(state)
    state.finish_success("Done.")

    store.write_task_state(state)
    store.write_report(state, {"task_state": state.to_dict(), "stop_reason": state.stop_reason})

    report = json.loads(store.report_path(state.run_id).read_text(encoding="utf-8"))
    assert report["stop_reason"] == STOP_REASON_FINAL_ANSWER_RETURNED
    assert report["task_state"]["final_answer"] == "Done."


def test_run_store_tolerates_missing_final_report(tmp_path):
    store = RunStore(tmp_path / ".teddycode" / "runs")
    state = TaskState.create(run_id="run_004", task_id="task_004", user_request="Crash before finalize.")

    store.start_run(state)
    store.append_trace(state, {"event": "run_started"})

    assert store.trace_path(state.run_id).exists()
    assert not store.report_path(state.run_id).exists()


def test_run_store_retries_transient_permission_error_during_atomic_replace(
    tmp_path, monkeypatch
):
    store = RunStore(tmp_path / ".teddycode" / "runs")
    state = TaskState.create(
        run_id="run_retry", task_id="task_retry", user_request="Retry a locked file."
    )
    real_replace = run_store_module.os.replace
    replace_attempts = []

    def flaky_replace(source, destination):
        replace_attempts.append((source, destination))
        if len(replace_attempts) < 3:
            raise PermissionError(13, "destination is temporarily locked")
        return real_replace(source, destination)

    monkeypatch.setattr(run_store_module.os, "replace", flaky_replace)
    monkeypatch.setattr(run_store_module.time, "sleep", lambda _delay: None)

    store.start_run(state)

    assert len(replace_attempts) == 3
    assert store.load_task_state(state.run_id)["task_id"] == "task_retry"
    assert list(store.run_dir(state.run_id).glob("task_state.json.*.tmp")) == []


def test_run_store_cleans_temp_file_after_persistent_permission_error(
    tmp_path, monkeypatch
):
    store = RunStore(tmp_path / ".teddycode" / "runs")
    state = TaskState.create(
        run_id="run_locked", task_id="task_locked", user_request="Stay locked."
    )
    def always_locked(_source, _destination):
        raise PermissionError(13, "destination remains locked")

    monkeypatch.setattr(run_store_module.os, "replace", always_locked)
    monkeypatch.setattr(run_store_module.time, "sleep", lambda _delay: None)

    with pytest.raises(PermissionError, match="destination remains locked"):
        store.start_run(state)

    assert list(store.run_dir(state.run_id).glob("task_state.json.*.tmp")) == []
