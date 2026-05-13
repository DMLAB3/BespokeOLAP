from __future__ import annotations

import json
from types import SimpleNamespace

import dspy
import pytest

from llm_cache.dspy_runtime import (
    DspyBespokeAgent,
    DspySessionStore,
    DspyToolbox,
    DspyWandbCallback,
)
from utils.model_setup import (
    DEFAULT_DSPY_INSTRUCTOR_MODEL,
    DEFAULT_DSPY_MODEL,
    setup_dspy_instructor_model_config,
    setup_dspy_model_config,
)


class FakeSnapshotter:
    def __init__(self, working_dir):
        self.working_dir = working_dir
        self.current_hash = "initial"
        self.snapshots: set[str] = set()
        self.restored: list[str] = []
        self.pushed = 0

    def is_dirty(self):
        return False

    def has_snapshot(self, value):
        return value in self.snapshots

    def fetch_snapshots(self):
        pass

    def clear_untracked(self, include_ignored):
        pass

    def reset_changes(self):
        pass

    def restore(self, value):
        self.restored.append(value)
        self.current_hash = value

    def snapshot(self, req_hash):
        commit = f"commit-{len(self.snapshots) + 1}"
        self.snapshots.add(commit)
        self.current_hash = commit
        return req_hash, commit

    def push_snapshots(self):
        self.pushed += 1


class FakeCompileTool:
    def __call__(self, optimize: bool) -> str:
        return f"compiled optimize={optimize}"


class FakeRunTool:
    def __call__(
        self,
        scale_factor: float,
        optimize: bool,
        query_id: list[str] | None = None,
        trace_mode: bool = False,
    ) -> str:
        return (
            f"ran sf={scale_factor} optimize={optimize} "
            f"query_id={query_id} trace={trace_mode}"
        )


class FakeProgram:
    def __init__(self):
        self.calls = 0
        self.last_kwargs = None

    def __call__(self, **kwargs):
        self.calls += 1
        self.last_kwargs = kwargs
        return SimpleNamespace(final_output=f"final {self.calls}")


class FakeInstructorProgram:
    def __call__(self, **kwargs):
        return SimpleNamespace(worker_guidance="Prefer small, verified edits.")


def test_setup_dspy_model_config_requires_gemini_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        setup_dspy_model_config()


def test_setup_dspy_model_config_default_and_override(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    model_name, lm = setup_dspy_model_config()
    assert model_name == DEFAULT_DSPY_MODEL
    assert lm.model == DEFAULT_DSPY_MODEL

    model_name, lm = setup_dspy_model_config("gemini/custom-model")
    assert model_name == "gemini/custom-model"
    assert lm.model == "gemini/custom-model"


def test_setup_dspy_model_config_installs_callbacks(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    callback = object()

    setup_dspy_model_config(callbacks=[callback])

    assert dspy.settings.callbacks == [callback]


def test_setup_dspy_instructor_model_config_default_and_override(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    model_name, lm = setup_dspy_instructor_model_config()
    assert model_name == DEFAULT_DSPY_INSTRUCTOR_MODEL
    assert lm.model == DEFAULT_DSPY_INSTRUCTOR_MODEL

    model_name, lm = setup_dspy_instructor_model_config("gemini/custom-pro")
    assert model_name == "gemini/custom-pro"
    assert lm.model == "gemini/custom-pro"


def test_dspy_toolbox_wraps_patch_compile_and_run(tmp_path):
    toolbox = DspyToolbox(
        workspace_path=tmp_path,
        cache_path=tmp_path / "cache",
        snapshotter=FakeSnapshotter(tmp_path),  # type: ignore[arg-type]
        compile_tool=FakeCompileTool(),  # type: ignore[arg-type]
        run_tool=FakeRunTool(),  # type: ignore[arg-type]
        wandb_metrics_hook=None,
    )

    assert toolbox.apply_patch("create_file", "created.txt", "+hello\n") == (
        "Created created.txt"
    )
    assert (tmp_path / "created.txt").read_text() == "hello"
    assert toolbox.compile(True) == "compiled optimize=True"
    assert toolbox.run(1, False, ["1"], True) == (
        "ran sf=1 optimize=False query_id=['1'] trace=True"
    )


def test_dspy_run_cache_replays_final_output_and_restores_snapshot(tmp_path):
    snapshotter = FakeSnapshotter(tmp_path)
    toolbox = DspyToolbox(
        workspace_path=tmp_path,
        cache_path=tmp_path / "cache",
        snapshotter=snapshotter,  # type: ignore[arg-type]
        compile_tool=None,
        run_tool=None,
        wandb_metrics_hook=None,
    )
    agent = DspyBespokeAgent(
        model_name="gemini/test",
        lm=dspy.LM("gemini/test", api_key="test-key"),
        tools=toolbox,
        llm_cache_dir=tmp_path / "llm-cache",
        snapshotter=snapshotter,  # type: ignore[arg-type]
        workspace_path=tmp_path,
    )
    fake_program = FakeProgram()
    agent.program = fake_program  # type: ignore[assignment]

    kwargs = dict(
        task="write a file",
        conversation_context="none",
        workspace_contract="contract",
        max_turns=2,
    )
    assert agent.run(**kwargs) == "final 1"
    assert fake_program.calls == 1
    assert agent.llm_was_cached is False

    assert agent.run(**kwargs) == "final 1"
    assert fake_program.calls == 1
    assert agent.llm_was_cached is True
    assert snapshotter.restored == ["commit-1"]


def test_dspy_run_cache_disabled_without_snapshotter(tmp_path):
    toolbox = DspyToolbox(
        workspace_path=tmp_path,
        cache_path=tmp_path / "cache",
        snapshotter=None,
        compile_tool=None,
        run_tool=None,
        wandb_metrics_hook=None,
    )
    agent = DspyBespokeAgent(
        model_name="gemini/test",
        lm=dspy.LM("gemini/test", api_key="test-key"),
        tools=toolbox,
        llm_cache_dir=tmp_path / "llm-cache",
        snapshotter=None,
        workspace_path=tmp_path,
    )
    fake_program = FakeProgram()
    agent.program = fake_program  # type: ignore[assignment]

    kwargs = dict(
        task="write a file",
        conversation_context="none",
        workspace_contract="contract",
        max_turns=2,
    )
    assert agent.run(**kwargs) == "final 1"
    assert agent.run(**kwargs) == "final 2"
    assert fake_program.calls == 2
    assert agent.llm_was_cached is False


def test_dspy_agent_prepends_rlm_instructor_guidance(tmp_path):
    toolbox = DspyToolbox(
        workspace_path=tmp_path,
        cache_path=tmp_path / "cache",
        snapshotter=None,
        compile_tool=None,
        run_tool=None,
        wandb_metrics_hook=None,
    )
    agent = DspyBespokeAgent(
        model_name="gemini/worker",
        lm=dspy.LM("gemini/worker", api_key="test-key"),
        tools=toolbox,
        llm_cache_dir=tmp_path / "llm-cache",
        snapshotter=None,
        workspace_path=tmp_path,
        instructor_model_name="gemini/instructor",
        instructor_lm=dspy.LM("gemini/instructor", api_key="test-key"),
    )
    fake_program = FakeProgram()
    agent.program = fake_program  # type: ignore[assignment]
    agent.instruction_program = FakeInstructorProgram()  # type: ignore[assignment]

    assert (
        agent.run(
            task="write a file",
            conversation_context="none",
            workspace_contract="contract",
            max_turns=2,
        )
        == "final 1"
    )
    assert fake_program.last_kwargs is not None
    assert "contract" in fake_program.last_kwargs["workspace_contract"]
    assert (
        "RLM instructor guidance for the worker model"
        in fake_program.last_kwargs["workspace_contract"]
    )
    assert (
        "Prefer small, verified edits."
        in fake_program.last_kwargs["workspace_contract"]
    )


def test_dspy_session_store_persists_summary_and_recent_turns(tmp_path):
    path = tmp_path / "session.json"
    store = DspySessionStore(path)
    store.append_turn("prompt 1", "output 1", branch_id="main")
    store.append_turn("prompt 2", "output 2", branch_id="main")

    context = store.render_context(branch_id="main")
    assert "prompt 1" in context
    assert "output 2" in context

    store.compact("short summary", branch_id="main")
    reloaded = DspySessionStore(path)
    assert reloaded.get_summary("main") == "short summary"
    assert "Summary:\nshort summary" in reloaded.render_context(branch_id="main")


def test_dspy_wandb_callback_logs_when_run_is_active(monkeypatch):
    logged = []
    monkeypatch.setattr("llm_cache.dspy_runtime.wandb.run", object())
    monkeypatch.setattr(
        "llm_cache.dspy_runtime.wandb.log",
        lambda payload, step=None, commit=None: logged.append(
            (payload, step, commit)
        ),
    )
    hook = SimpleNamespace(disable=False, last_turn=7)
    callback = DspyWandbCallback(hook)  # type: ignore[arg-type]

    callback.on_lm_start("abc", object(), {"prompt": "hello"})
    callback.on_lm_end("abc", {"text": "world"})

    assert logged[0][0]["dspy/event"] == "lm_start"
    assert logged[0][1] == 7
    assert logged[0][2] is False
    assert logged[1][0]["dspy/event"] == "lm_end"
    assert logged[1][0]["dspy/lm_ok"] is True


def test_dspy_callback_writes_full_lm_request_response_locally(tmp_path):
    path = tmp_path / "llm_calls.jsonl"
    callback = DspyWandbCallback(None, llm_log_path=path)
    lm = SimpleNamespace(model="gemini/test", model_type="chat", history=[])

    callback.on_lm_start("abc", lm, {"messages": [{"role": "user", "content": "hi"}]})
    lm.history.append(
        {
            "messages": [{"role": "user", "content": "hi"}],
            "response": {"text": "hello"},
        }
    )
    callback.on_lm_end("abc", ["hello"])

    records = [json.loads(line) for line in path.read_text().splitlines()]
    assert len(records) == 1
    assert records[0]["call_id"] == "abc"
    assert records[0]["model"] == "gemini/test"
    assert records[0]["request"]["messages"][0]["content"] == "hi"
    assert records[0]["response"] == ["hello"]
    assert records[0]["history_entry"]["response"]["text"] == "hello"
