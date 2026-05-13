from __future__ import annotations

from typing import Protocol


class CompilePort(Protocol):
    def __call__(self, optimize: bool) -> str:
        ...


class RunPort(Protocol):
    def __call__(
        self,
        scale_factor: float,
        optimize: bool,
        query_id: list[str] | None = None,
        trace_mode: bool = False,
    ) -> str:
        ...
