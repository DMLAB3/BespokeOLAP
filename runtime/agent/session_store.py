from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from llm_cache import utils

logger = logging.getLogger(__name__)


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
        artifacts_in_context: str | None = None,
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

        if artifacts_in_context:
            artifacts_text = artifacts_in_context.strip()
            if artifacts_text:
                sections.append("Workspace artifacts:\n" + artifacts_text)

        return "\n\n".join(sections) if sections else "No prior conversation context."
