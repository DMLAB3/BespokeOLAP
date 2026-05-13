from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import dspy

from llm_cache import utils
from llm_cache.git_snapshotter import GitSnapshotter
from runtime.agent.toolbox import DspyToolbox
from utils.truncate_csv import truncate_csvs_recursively
from utils.wandb_stats_logging import WandbRunHook

logger = logging.getLogger(__name__)


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


RLM_INSTRUCTOR_SIGNATURE = (
    "task, conversation_context, workspace_contract, artifacts_in_context "
    "-> worker_guidance"
)


@dataclass
class DspyCacheEntry:
    final_output: str
    parent_hash: str | None = None
    usage: dict[str, Any] | None = None


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
        instructor_model_name: str | None = None,
        instructor_lm: dspy.LM | None = None,
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
        self.instructor_model_name = instructor_model_name
        self.instructor_lm = instructor_lm
        self.total_saved = 0.0
        self.llm_was_cached = False
        self.program = dspy.ReAct(
            BespokeAgentSignature,
            tools=self.tools.enabled_tools(),
            max_iters=20,
        )
        self.instruction_program = (
            dspy.RLM(
                RLM_INSTRUCTOR_SIGNATURE,
                max_iterations=12,
                max_llm_calls=24,
                max_output_chars=40_000,
                sub_lm=self.lm,
                verbose=False,
            )
            if self.instructor_lm is not None
            else None
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
            "instructor_model": self.instructor_model_name,
        }
        return utils.sha256(utils.stable_json(payload))

    def _write_worker_instructions(
        self,
        *,
        task: str,
        conversation_context: str,
        workspace_contract: str,
    ) -> str:
        if self.instruction_program is None or self.instructor_lm is None:
            return workspace_contract

        with dspy.context(lm=self.instructor_lm):
            pred = self.instruction_program(
                task=task,
                conversation_context=conversation_context,
                workspace_contract=workspace_contract,
                artifacts_in_context=self.artifacts_in_context or "",
            )
        instructions = str(getattr(pred, "worker_guidance", pred)).strip()
        if not instructions:
            return workspace_contract
        return "\n\n".join(
            [
                workspace_contract,
                "RLM instructor guidance for the worker model:",
                instructions,
            ]
        )

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
        workspace_contract = self._write_worker_instructions(
            task=task,
            conversation_context=conversation_context,
            workspace_contract=workspace_contract,
        )
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
