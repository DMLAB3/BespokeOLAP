#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _dir_size(path: Path) -> int | None:
    if not path.exists():
        return None
    if path.is_file():
        return path.stat().st_size

    total = 0
    for child in path.rglob("*"):
        try:
            if child.is_file():
                total += child.stat().st_size
        except OSError:
            continue
    return total


def _format_bytes(size: int | None) -> str:
    if size is None:
        return "-"
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} {unit}"
        value /= 1024
    raise AssertionError("unreachable")


def _path_info(name: str, path: Path) -> dict[str, object]:
    resolved = path.expanduser().resolve()
    size = _dir_size(resolved)
    return {
        "name": name,
        "path": resolved.as_posix(),
        "exists": resolved.exists(),
        "size_bytes": size,
        "size": _format_bytes(size),
    }


def collect_locations(artifacts_dir: Path) -> list[dict[str, object]]:
    repo_root = _repo_root()

    weave_cache = Path(
        os.environ.get(
            "WEAVE_SERVER_CACHE_DIR",
            (Path.home() / ".cache" / "weave" / "server_cache").as_posix(),
        )
    )
    wandb_dir = Path(os.environ.get("WANDB_DIR", repo_root / "wandb"))

    return [
        _path_info("Weave trace server cache", weave_cache),
        _path_info("W&B run directory", wandb_dir),
        _path_info("Project artifact cache", artifacts_dir / "cache"),
        _path_info("LLM cache", artifacts_dir / "cache" / "llm_cache"),
        _path_info("Compaction cache", artifacts_dir / "cache" / "compaction"),
        _path_info("Shell cache", artifacts_dir / "cache" / "shell"),
        _path_info("Validation cache", artifacts_dir / "cache" / "validate_tool"),
    ]


def main() -> None:
    repo_root = _repo_root()
    _load_dotenv(repo_root / ".env")

    parser = argparse.ArgumentParser(
        description="Print local W&B, Weave trace, and BespokeOLAP cache locations."
    )
    parser.add_argument(
        "--artifacts-dir",
        default="/home/mk/",
        type=Path,
        help="Artifacts directory used by the run config. Defaults to /home/mk/.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON.",
    )
    args = parser.parse_args()

    locations = collect_locations(args.artifacts_dir.expanduser())

    if args.json:
        print(json.dumps(locations, indent=2))
        return

    width = max(len(item["name"]) for item in locations)
    for item in locations:
        exists = "exists" if item["exists"] else "missing"
        print(
            f"{item['name']:<{width}}  {exists:7}  {item['size']:>10}  {item['path']}"
        )


if __name__ == "__main__":
    main()
