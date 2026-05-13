from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RuntimeConfig:
    """Typed runtime settings used by the orchestrator layer."""

    benchmark: str
    conv_name: str
    query_list: str
    artifacts_dir: Path
    base_parquet_dir: Path
    conv_mode: str
    continue_run: bool
    replay: bool
    disable_tracing: bool
    disable_wandb: bool
    model: str
