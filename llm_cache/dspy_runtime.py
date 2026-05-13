from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import dspy
import wandb
from dspy.utils.callback import BaseCallback

from . import utils
from .git_snapshotter import GitSnapshotter
from tools.fasttest.compile import CompileTool
from tools.fasttest.run import RunTool
from tools.litellm_apply_patch import LitellmApplyPatchTool
from tools.litellm_shell import LitellmShellTool
from utils.truncate_csv import truncate_csvs_recursively
from utils.wandb_stats_logging import WandbRunHook

logger = logging.getLogger(__name__)


def _truncate_for_log(value: Any, max_chars: int = 2000) -> str:
    try:
        text = utils.stable_json(value)
    except Exception:
        text = repr(value)
    if len(text) > max_chars:
        return text[:max_chars] + "...<truncated>"
    return text


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    if hasattr(value, "model_dump"):
        try:
            return _json_safe(value.model_dump())
        except Exception:
            pass
    if hasattr(value, "to_dict"):
        try:
            return _json_safe(value.to_dict())
        except Exception:
            pass
    try:
        json.dumps(value)
        return value
    except Exception:
        return repr(value)


class LLMRequestResponseLogger:
    """Append full DSPy LM request/response records as JSON Lines."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def write(self, record: dict[str, Any]) -> None:
        line = json.dumps(_json_safe(record), ensure_ascii=False, sort_keys=True)
        with self._lock:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")


class DspyWandbCallback(BaseCallback):
    """DSPy callback that logs native module/LM/tool events to the active W&B run."""

    def __init__(
        self,
        wandb_metrics_hook: WandbRunHook | None,
        *,
        log_payloads: bool = True,
        llm_log_path: Path | None = None,
    ) -> None:
        self.wandb_metrics_hook = wandb_metrics_hook
        self.log_payloads = log_payloads
        self._starts: dict[str, float] = {}
        self._lm_requests: dict[str, dict[str, Any]] = {}
        self._llm_logger = (
            LLMRequestResponseLogger(llm_log_path) if llm_log_path is not None else None
        )

    def _enabled(self) -> bool:
        if self.wandb_metrics_hook is None or self.wandb_metrics_hook.disable:
            return False
        return wandb.run is not None

    def _step(self) -> int:
        if self.wandb_metrics_hook is None:
            return 0
        return self.wandb_metrics_hook.last_turn

    def _log(self, payload: dict[str, Any]) -> None:
        if not self._enabled():
            return
        wandb.log(payload, step=self._step(), commit=False)

    def _start(self, call_id: str, event_type: str, instance: Any, inputs: dict[str, Any]) -> None:
        self._starts[call_id] = time.monotonic()
        payload: dict[str, Any] = {
            "dspy/event": f"{event_type}_start",
            "dspy/call_id": call_id,
            f"dspy/{event_type}_name": type(instance).__name__,
        }
        if self.log_payloads:
            payload[f"dspy/{event_type}_inputs"] = _truncate_for_log(inputs)
        self._log(payload)

    def _end(
        self,
        call_id: str,
        event_type: str,
        outputs: Any | None,
        exception: Exception | None,
    ) -> None:
        started_at = self._starts.pop(call_id, None)
        payload: dict[str, Any] = {
            "dspy/event": f"{event_type}_end",
            "dspy/call_id": call_id,
            f"dspy/{event_type}_error": str(exception) if exception else "",
            f"dspy/{event_type}_ok": exception is None,
        }
        if started_at is not None:
            payload[f"dspy/{event_type}_duration_sec"] = time.monotonic() - started_at
        if self.log_payloads:
            payload[f"dspy/{event_type}_outputs"] = _truncate_for_log(outputs)
        self._log(payload)

    def on_module_start(self, call_id: str, instance: Any, inputs: dict[str, Any]):
        self._start(call_id, "module", instance, inputs)

    def on_module_end(
        self,
        call_id: str,
        outputs: Any | None,
        exception: Exception | None = None,
    ):
        self._end(call_id, "module", outputs, exception)

    def on_lm_start(self, call_id: str, instance: Any, inputs: dict[str, Any]):
        self._lm_requests[call_id] = {
            "call_id": call_id,
            "model": getattr(instance, "model", None),
            "model_type": getattr(instance, "model_type", None),
            "request": inputs,
            "started_at": time.time(),
            "started_at_monotonic": time.monotonic(),
            "history_len_before": len(getattr(instance, "history", []) or []),
            "_instance": instance,
        }
        self._start(call_id, "lm", instance, inputs)

    def on_lm_end(
        self,
        call_id: str,
        outputs: dict[str, Any] | None,
        exception: Exception | None = None,
    ):
        request = self._lm_requests.pop(call_id, {})
        instance = request.pop("_instance", None)
        started_at_monotonic = request.pop("started_at_monotonic", None)
        history_entry = None
        if instance is not None:
            history = getattr(instance, "history", []) or []
            history_len_before = int(request.get("history_len_before") or 0)
            if len(history) > history_len_before:
                history_entry = history[-1]

        record = {
            **request,
            "response": outputs,
            "exception": str(exception) if exception else None,
            "ended_at": time.time(),
            "duration_sec": (
                time.monotonic() - started_at_monotonic
                if started_at_monotonic is not None
                else None
            ),
            "history_entry": history_entry,
        }
        if self._llm_logger is not None:
            self._llm_logger.write(record)
        self._end(call_id, "lm", outputs, exception)

    def on_tool_start(self, call_id: str, instance: Any, inputs: dict[str, Any]):
        self._start(call_id, "tool", instance, inputs)

    def on_tool_end(
        self,
        call_id: str,
        outputs: dict[str, Any] | None,
        exception: Exception | None = None,
    ):
        self._end(call_id, "tool", outputs, exception)


class BespokeAgentSignature(dspy.Signature):
    """Use the available workspace tools to complete the requested database-engine task."""

    task: str = dspy.InputField(desc="Current user task or conversation prompt.")
    conversation_context: str = dspy.InputField(
        desc="Prior accepted prompts, outputs, and any compacted summary."
    )
    workspace_contract: str = dspy.InputField(
        desc="Workspace rules and available tool usage instructions."
    )
    final_output: str = dspy.OutputField(
        desc="The concise final response after all required tool work is complete."
    )


class ConversationSummary(dspy.Signature):
    """Compact a long agent conversation while preserving implementation-critical state."""

    existing_summary: str = dspy.InputField()
    recent_context: str = dspy.InputField()
    summary: str = dspy.OutputField(
        desc="A compact summary of durable decisions, files changed, errors, and next steps."
    )


@dataclass
class DspyCacheEntry:
    final_output: str
    parent_hash: str | None = None
    usage: dict[str, Any] | None = None


def _run_coro_sync(coro):
    """Run an async tool implementation from DSPy's synchronous tool calls."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    if not loop.is_running():
        return loop.run_until_complete(coro)

    result: dict[str, Any] = {}

    def runner() -> None:
        try:
            result["value"] = asyncio.run(coro)
        except BaseException as exc:  # pragma: no cover - re-raised in caller thread.
            result["error"] = exc

    thread = threading.Thread(target=runner)
    thread.start()
    thread.join()
    if "error" in result:
        raise result["error"]
    return result.get("value")


def _message_content(item: Any) -> str:
    if not isinstance(item, dict):
        return str(item)
    content = item.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict):
                value = part.get("text") or part.get("content")
                if value is not None:
                    parts.append(str(value))
            else:
                parts.append(str(part))
        return "\n".join(parts)
    return str(content)


class DspySessionStore:
    """Small JSON store for DSPy summaries and branch-local recent turns."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"version": 1, "branches": {}}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data.setdefault("version", 1)
                data.setdefault("branches", {})
                return data
        except Exception:
            logger.exception("Failed to load DSPy session store %s", self.path)
        return {"version": 1, "branches": {}}

    def _save(self) -> None:
        payload = json.dumps(self.data, indent=2, sort_keys=True)
        utils.atomic_write(self.path, payload.encode("utf-8"))

    def _branch(self, branch_id: str | None) -> dict[str, Any]:
        key = branch_id or "main"
        branches = self.data.setdefault("branches", {})
        branch = branches.setdefault(key, {"summary": "", "turns": []})
        branch.setdefault("summary", "")
        branch.setdefault("turns", [])
        return branch

    def append_turn(self, prompt: str, output: str, branch_id: str | None = None) -> None:
        branch = self._branch(branch_id)
        branch["turns"].append({"prompt": prompt, "output": output})
        branch["turns"] = branch["turns"][-20:]
        self._save()

    def get_summary(self, branch_id: str | None = None) -> str:
        return str(self._branch(branch_id)["summary"])

    def compact(self, summary: str, branch_id: str | None = None) -> None:
        branch = self._branch(branch_id)
        branch["summary"] = summary
        branch["turns"] = branch["turns"][-2:]
        self._save()

    def render_context(
        self,
        branch_id: str | None = None,
        session_items: list[Any] | None = None,
        max_turns: int = 6,
    ) -> str:
        branch = self._branch(branch_id)
        sections: list[str] = []
        if branch["summary"]:
            sections.append(f"Summary:\n{branch['summary']}")

        if session_items:
            recent = session_items[-max_turns * 2 :]
            lines = []
            for item in recent:
                role = item.get("role", "item") if isinstance(item, dict) else "item"
                lines.append(f"{role}: {_message_content(item)}")
            if lines:
                sections.append("Recent branch messages:\n" + "\n\n".join(lines))
        elif branch["turns"]:
            turns = branch["turns"][-max_turns:]
            lines = [
                f"user: {turn['prompt']}\nassistant: {turn['output']}"
                for turn in turns
            ]
            sections.append("Recent turns:\n" + "\n\n".join(lines))

        return "\n\n".join(sections) if sections else "No prior conversation context."


class DspyToolbox:
    def __init__(
        self,
        *,
        workspace_path: Path,
        cache_path: Path,
        snapshotter: GitSnapshotter | None,
        compile_tool: CompileTool | None,
        run_tool: RunTool | None,
        wandb_metrics_hook: WandbRunHook | None,
    ) -> None:
        self._shell = LitellmShellTool(
            cwd=workspace_path,
            cache_dir=cache_path / "shell",
            git_snapshotter=snapshotter,
            wandb_metrics_hook=wandb_metrics_hook,
        )
        self._apply_patch = LitellmApplyPatchTool(
            root=workspace_path,
            wandb_metrics_hook=wandb_metrics_hook,
        )
        self._compile_tool = compile_tool
        self._run_tool = run_tool
        self._wandb_metrics_hook = wandb_metrics_hook

    def shell(self, command: str, timeout_ms: int | None = None) -> str:
        """Run a shell command inside the workspace sandbox."""
        return _run_coro_sync(self._shell(command=command, timeout_ms=timeout_ms))

    def apply_patch(self, op_type: str, path: str, diff: str | None = None) -> str:
        """Apply a patch. op_type must be create_file, update_file, or delete_file."""
        if self._wandb_metrics_hook is not None:
            self._wandb_metrics_hook.apply_patch_added_ctr = 0
            self._wandb_metrics_hook.apply_patch_deleted_ctr = 0
        result = _run_coro_sync(
            self._apply_patch(op_type=op_type, path=path, diff=diff)
        )
        if self._wandb_metrics_hook is not None:
            self._wandb_metrics_hook.log_metrics_callback(
                {
                    "type": "apply_patch_tool",
                    "apply_patch/added_loc_count": (
                        self._wandb_metrics_hook.apply_patch_added_ctr
                    ),
                    "apply_patch/deleted_loc_count": (
                        self._wandb_metrics_hook.apply_patch_deleted_ctr
                    ),
                },
                log_and_increment=True,
            )
        return result

    def compile(self, optimize: bool) -> str:
        """Compile the database. Set optimize true for -O3/-flto builds."""
        if self._compile_tool is None:
            return "compile tool is not available for this conversation"
        return self._compile_tool(optimize=optimize)

    def run(
        self,
        scale_factor: float,
        optimize: bool,
        query_id: list[str] | None = None,
        trace_mode: bool = False,
    ) -> str:
        """Run the database for query IDs. query_id omitted means all queries."""
        if self._run_tool is None:
            return "run tool is not available for this conversation"
        return self._run_tool(
            scale_factor=scale_factor,
            optimize=optimize,
            query_id=query_id,
            trace_mode=trace_mode,
        )

    def enabled_tools(self) -> list[Callable[..., str]]:
        tools: list[Callable[..., str]] = [self.shell, self.apply_patch]
        if self._compile_tool is not None:
            tools.append(self.compile)
        if self._run_tool is not None:
            tools.append(self.run)
        return tools

    def schema_payload(self) -> list[dict[str, Any]]:
        payload = []
        for tool in self.enabled_tools():
            payload.append(
                {
                    "name": tool.__name__,
                    "annotations": {
                        key: str(value)
                        for key, value in getattr(tool, "__annotations__", {}).items()
                    },
                    "doc": tool.__doc__ or "",
                }
            )
        return payload


class DspyBespokeAgent:
    def __init__(
        self,
        *,
        model_name: str,
        lm: dspy.LM,
        tools: DspyToolbox,
        llm_cache_dir: Path,
        snapshotter: GitSnapshotter | None,
        workspace_path: Path,
        stop_on_cache_miss: bool = False,
        query_gen_list: list[str] | None = None,
        artifacts_in_context: str | None = None,
        config_kwargs: dict[str, Any] | None = None,
        callbacks: list[Any] | None = None,
    ) -> None:
        self.model_name = model_name
        self.lm = lm
        self.tools = tools
        self.cache_dir = llm_cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.snapshotter = snapshotter
        self.workspace_path = workspace_path
        self.stop_on_cache_miss = stop_on_cache_miss
        self.query_gen_list = query_gen_list
        self.artifacts_in_context = artifacts_in_context
        self.config_kwargs = config_kwargs or {}
        self.callbacks = callbacks or []
        self.total_saved = 0.0
        self.llm_was_cached = False
        self.program = dspy.ReAct(
            BespokeAgentSignature,
            tools=self.tools.enabled_tools(),
            max_iters=20,
        )
        dspy.configure(lm=self.lm, track_usage=True, callbacks=self.callbacks)

    def __str__(self) -> str:
        return self.model_name

    def _cache_path_for(self, hash_value: str) -> Path:
        return self.cache_dir / f"{hash_value}.pkl"

    def _hash_payload(
        self,
        *,
        task: str,
        conversation_context: str,
        workspace_contract: str,
        max_turns: int,
    ) -> str:
        payload = {
            "model": self.model_name,
            "task": task,
            "conversation_context": conversation_context,
            "workspace_contract": workspace_contract,
            "max_turns": max_turns,
            "tools": self.tools.schema_payload(),
            "query_gen_list": self.query_gen_list,
            "artifacts_in_context": self.artifacts_in_context,
            "config_kwargs": self.config_kwargs,
        }
        return utils.sha256(utils.stable_json(payload))

    def _restore_cached_snapshot(self, entry: DspyCacheEntry, path: Path) -> bool:
        if self.snapshotter is None:
            return False
        if not entry.parent_hash:
            if self.snapshotter.is_dirty():
                raise RuntimeError("No parent hash and directory is dirty")
            return True

        exists = self.snapshotter.has_snapshot(entry.parent_hash)
        if not exists:
            self.snapshotter.fetch_snapshots()
            exists = self.snapshotter.has_snapshot(entry.parent_hash)
        if not exists:
            msg = (
                f"DSPy cache entry {path} references missing snapshot "
                f"{entry.parent_hash}; treating it as a cache miss."
            )
            if self.stop_on_cache_miss:
                raise RuntimeError(msg)
            logger.warning(msg)
            return False

        self.snapshotter.clear_untracked(include_ignored=True)
        self.snapshotter.reset_changes()
        self.snapshotter.restore(entry.parent_hash)
        return True

    def _usage_since(self, start_history_len: int) -> dict[str, Any]:
        history = getattr(self.lm, "history", []) or []
        entries = history[start_history_len:]
        usage = {
            "num_llm_request": len(entries),
            "input_tokens": 0,
            "output_tokens": 0,
            "cached_tokens": 0,
            "reasoning_tokens": 0,
            "cost": 0.0,
            "context_window_usage": 0.0,
        }
        for entry in entries:
            raw_usage = None
            if isinstance(entry, dict):
                raw_usage = entry.get("usage")
                response = entry.get("response")
                if raw_usage is None and isinstance(response, dict):
                    raw_usage = response.get("usage")
                elif raw_usage is None and hasattr(response, "usage"):
                    raw_usage = getattr(response, "usage")
            if raw_usage is None:
                continue
            if not isinstance(raw_usage, dict):
                raw_usage = dict(raw_usage)
            usage["input_tokens"] += int(
                raw_usage.get("prompt_tokens")
                or raw_usage.get("input_tokens")
                or raw_usage.get("total_input_tokens")
                or 0
            )
            usage["output_tokens"] += int(
                raw_usage.get("completion_tokens")
                or raw_usage.get("output_tokens")
                or raw_usage.get("total_output_tokens")
                or 0
            )
        return usage

    def _log_usage(
        self,
        usage: dict[str, Any],
        *,
        wandb_metrics_hook: WandbRunHook | None,
        prompt_idx: int,
        short_desc: str | None,
        task: str,
    ) -> None:
        if usage["num_llm_request"] <= 0:
            logger.info("DSPy usage unavailable for model %s", self.model_name)
            if wandb_metrics_hook is not None:
                wandb_metrics_hook.current_prompt = None
                wandb_metrics_hook.current_prompt_descriptor = None
            return

        logger.info(
            "DSPy LLM usage: requests=%s input=%s output=%s cost=$%0.6f",
            usage["num_llm_request"],
            usage["input_tokens"],
            usage["output_tokens"],
            usage["cost"],
        )

        if wandb_metrics_hook is None:
            return

        metrics = {
            "type": "llm_call",
            "prompt_idx": prompt_idx,
            "agent_name": "Bespoke DSPy Agent",
            "cost_usd": usage["cost"],
            "input_tokens": usage["input_tokens"],
            "cached_tokens": usage["cached_tokens"],
            "output_tokens": usage["output_tokens"],
            "reasoning_tokens": usage["reasoning_tokens"],
            "context_window_usage": usage["context_window_usage"],
            "current_prompt": task,
            "current_prompt_descriptor": short_desc,
        }
        wandb_metrics_hook.total_stats["input_tokens"] += usage["input_tokens"]
        wandb_metrics_hook.total_stats["cached_tokens"] += usage["cached_tokens"]
        wandb_metrics_hook.total_stats["output_tokens"] += usage["output_tokens"]
        wandb_metrics_hook.total_stats["reasoning_tokens"] += usage["reasoning_tokens"]
        wandb_metrics_hook.total_stats["cost_usd"] += usage["cost"]
        metrics.update(
            {
                "total/input_tokens": wandb_metrics_hook.total_stats["input_tokens"],
                "total/cached_tokens": wandb_metrics_hook.total_stats["cached_tokens"],
                "total/output_tokens": wandb_metrics_hook.total_stats["output_tokens"],
                "total/reasoning_tokens": wandb_metrics_hook.total_stats[
                    "reasoning_tokens"
                ],
                "total/cost_usd": wandb_metrics_hook.total_stats["cost_usd"],
            }
        )
        wandb_metrics_hook.log_metrics_callback(metrics, log_and_increment=True)
        wandb_metrics_hook.current_prompt = None
        wandb_metrics_hook.current_prompt_descriptor = None

    def run(
        self,
        *,
        task: str,
        conversation_context: str,
        workspace_contract: str,
        max_turns: int,
        wandb_metrics_hook: WandbRunHook | None = None,
        prompt_idx: int = 0,
        short_desc: str | None = None,
    ) -> str:
        req_hash = self._hash_payload(
            task=task,
            conversation_context=conversation_context,
            workspace_contract=workspace_contract,
            max_turns=max_turns,
        )
        path = self._cache_path_for(req_hash)

        use_run_cache = self.snapshotter is not None

        if use_run_cache and path.exists():
            cached = utils.load_pickle(path, DspyCacheEntry)
            if cached is not None and self._restore_cached_snapshot(cached, path):
                logger.debug("Read DSPy response from cache: %s", path.name)
                self.llm_was_cached = True
                return cached.final_output

        if self.stop_on_cache_miss and use_run_cache:
            raise RuntimeError(f"Stop on cache miss. Did not find in cache: {path}")
        if self.stop_on_cache_miss and not use_run_cache:
            logger.warning(
                "Run-level DSPy cache replay is disabled because git snapshots are disabled."
            )

        history_len = len(getattr(self.lm, "history", []) or [])
        pred = self.program(
            task=task,
            conversation_context=conversation_context,
            workspace_contract=workspace_contract,
            max_iters=max_turns,
        )
        final_output = str(getattr(pred, "final_output", pred))
        usage = self._usage_since(history_len)
        self._log_usage(
            usage,
            wandb_metrics_hook=wandb_metrics_hook,
            prompt_idx=prompt_idx,
            short_desc=short_desc,
            task=task,
        )

        max_workspace_csv_size_mb = self.config_kwargs.get(
            "max_workspace_csv_size_mb",
            self.config_kwargs.get("max_snapshot_csv_size_mb"),
        )
        if max_workspace_csv_size_mb is not None:
            truncate_csvs_recursively(
                self.workspace_path,
                max_size_mb=max_workspace_csv_size_mb,
            )

        if use_run_cache:
            assert self.snapshotter is not None
            _, commit = self.snapshotter.snapshot(req_hash)
            utils.dump_pickle(
                path, DspyCacheEntry(final_output, parent_hash=commit, usage=usage)
            )
            self.snapshotter.push_snapshots()
        self.llm_was_cached = False
        return final_output

    def compact_context(self, existing_summary: str, recent_context: str) -> str:
        summarizer = dspy.Predict(ConversationSummary)
        pred = summarizer(
            existing_summary=existing_summary,
            recent_context=recent_context,
        )
        return str(getattr(pred, "summary", ""))
