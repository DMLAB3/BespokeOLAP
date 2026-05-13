from __future__ import annotations

import re

_QUERY_ITEM_RE = re.compile(r"Query\s*(\d+)\s*:\s*([0-9]+(?:\.[0-9]+)?)")


def _parse_query_items(items: str) -> dict[str, float]:
    """Parse fragments like 'Query 1: 12.3, Query 2: 4.5' into a dict."""

    if not items.strip():
        return {}
    return {query_id: float(runtime_ms) for query_id, runtime_ms in _QUERY_ITEM_RE.findall(items)}


def _extract_sum(line: str) -> float:
    match = re.search(r"-\s*sum:\s*([0-9]+(?:\.[0-9]+)?)", line)
    if match is None:
        raise ValueError(f"Could not parse total runtime sum from line: {line}")
    return float(match.group(1))


def parse_old_runtime_report(report: str) -> dict[str, float | int | bool]:
    """Parse old validation output into metric dict used by tests and logging."""

    lines = [line.strip() for line in report.splitlines() if line.strip()]

    ingest_time_ms: int | None = None
    duckdb_query_runtimes: dict[str, float] = {}
    impl_query_runtimes: dict[str, float] = {}
    total_duckdb_runtime_ms: float | None = None
    total_impl_runtime_ms: float | None = None

    for line in lines:
        if line.startswith("Ingest time (ms):"):
            ingest_time_ms = int(float(line.split(":", maxsplit=1)[1].strip()))
            continue

        if line.startswith("DuckDB runtimes (ms):"):
            items_part = line.split(":", maxsplit=1)[1].strip()
            duckdb_query_runtimes = _parse_query_items(items_part)
            total_duckdb_runtime_ms = _extract_sum(line)
            continue

        if line.startswith("Your Implementation runtimes (ms):"):
            items_part = line.split(":", maxsplit=1)[1].strip()
            impl_query_runtimes = _parse_query_items(items_part)
            total_impl_runtime_ms = _extract_sum(line)
            continue

    if ingest_time_ms is None:
        raise ValueError("Missing ingest time in report")
    if total_duckdb_runtime_ms is None or total_impl_runtime_ms is None:
        raise ValueError("Missing runtime totals in report")

    shared_queries = sorted(set(duckdb_query_runtimes) & set(impl_query_runtimes), key=int)
    if not shared_queries:
        raise ValueError("No per-query runtime pairs were parsed")

    per_query_speedups: dict[str, float] = {}
    for query_id in shared_queries:
        impl_runtime = impl_query_runtimes[query_id]
        if impl_runtime <= 0.0:
            raise ValueError(f"Invalid impl runtime for query {query_id}: {impl_runtime}")
        per_query_speedups[query_id] = duckdb_query_runtimes[query_id] / impl_runtime

    avg_speedup = sum(per_query_speedups.values()) / len(per_query_speedups)
    total_speedup = total_duckdb_runtime_ms / total_impl_runtime_ms

    result: dict[str, float | int | bool] = {
        "validation/ingest_time_ms": ingest_time_ms,
        "validation/correct": "All results match!" in report,
        "validation/error": False,
        "validation/total_duckdb_runtime_ms": total_duckdb_runtime_ms,
        "validation/total_impl_runtime_ms": total_impl_runtime_ms,
        "validation/total_speedup": total_speedup,
        "validation/avg_speedup": avg_speedup,
        "validation/num_queries": len(shared_queries),
        "validation/num_successful_queries": len(shared_queries),
        "validation/all_queries": True,
        "validation/all_queries_avg_speedup": avg_speedup,
        "validation/all_queries_total_speedup": total_speedup,
    }

    for query_id in shared_queries:
        result[f"validation/query_{query_id}/duckdb_runtime_ms"] = duckdb_query_runtimes[query_id]
        result[f"validation/query_{query_id}/impl_runtime_ms"] = impl_query_runtimes[query_id]
        result[f"validation/query_{query_id}/speedup"] = per_query_speedups[query_id]

    return result
