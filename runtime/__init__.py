"""Runtime package for orchestration rewrite."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
	from runtime.orchestrator.runner import RuntimeRunner


def __getattr__(name: str):
	if name == "RuntimeRunner":
		from runtime.orchestrator.runner import RuntimeRunner

		return RuntimeRunner
	raise AttributeError(name)

__all__ = ["RuntimeRunner"]
