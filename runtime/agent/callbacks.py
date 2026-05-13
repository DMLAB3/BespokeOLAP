from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

import wandb
from dspy.utils.callback import BaseCallback

from llm_cache import utils
from utils.wandb_stats_logging import WandbRunHook


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
