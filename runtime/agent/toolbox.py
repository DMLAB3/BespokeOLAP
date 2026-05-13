from __future__ import annotations

import asyncio
import threading
from pathlib import Path
from typing import Any, Callable

from llm_cache.git_snapshotter import GitSnapshotter
from tools.fasttest.compile import CompileTool
from tools.fasttest.run import RunTool
from tools.litellm_apply_patch import LitellmApplyPatchTool
from tools.litellm_shell import LitellmShellTool
from utils.wandb_stats_logging import WandbRunHook


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
