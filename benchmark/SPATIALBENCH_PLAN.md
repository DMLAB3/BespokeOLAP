# SpatialBench: Full Next-Step Implementation Plan

## 1. Objective
Build an experimental SpatialBench path that is reproducible, comparable against DuckDB, and usable inside the existing Bespoke-OLAP optimization loop.

Primary goals:
- Add a stable spatial benchmark workload (query set + data assumptions + metrics).
- Run SpatialBench through current benchmarking entry points.
- Keep validation and performance measurement aligned with existing tpch/ceb workflows.

Non-goals for first iteration:
- Perfect geospatial semantics for every edge case.
- Distributed execution.
- New external infrastructure beyond current local pipeline.

## 2. Current State (Already Done)
Spatial scaffold exists for:
- Query template + placeholder generation.
- Spatial benchmark routing in benchmark selection.
- Basic dataset/schema metadata hooks.
- README-level documentation for experimental status.

This plan focuses on turning that scaffold into a full benchmark workflow.

## 3. Delivery Strategy
Use 4 milestones:
- Milestone A: Benchmark spec and baseline correctness.
- Milestone B: Runner/validation integration and reproducible outputs.
- Milestone C: Bespoke spatial execution path + optimization hooks.
- Milestone D: Hardening (tests, docs, CI checks, acceptance run).

---

## 4. Milestone A: Benchmark Specification

### A1. Freeze SpatialBench query contract
Define each benchmark query with:
- Query intent (e.g., point-in-polygon, radius search).
- Required placeholders and valid ranges.
- Expected output schema and ordering rules.
- Determinism rules (seeded generation and stable tie-breaking).

Acceptance:
- Query contract documented in benchmark docs.
- Every query has deterministic parameter generation from fixed seeds.

### A2. Freeze data contract
Define required input tables/columns and geometry encoding:
- Preferred first-pass format: coordinate columns + canonical geometry expression in SQL.
- Explicit SRID/unit assumptions.
- Null/invalid geometry handling policy.

Acceptance:
- One canonical data contract document.
- Runner can assert contract violations early with actionable errors.

### A3. Define metric contract
For each run capture:
- Wall-clock execution time per query.
- Optional cold/warm split.
- Rows produced.
- Success/failure and validation status.

Acceptance:
- Metric schema fixed and reflected in benchmark CSV output.

---

## 5. Milestone B: End-to-End Baseline Pipeline (DuckDB First)

### B1. DuckDB spatial baseline verification
Ensure DuckDB path supports spatial SQL used by SpatialBench.

Tasks:
- Validate extension/function availability for spatial predicates used by queries.
- Add startup checks with explicit failure hints.
- Normalize function usage in query templates to avoid version drift.

Acceptance:
- `python -m benchmark --systems duckdb --benchmark spatial` runs successfully on prepared data.

### B2. Benchmark runner semantics
In [benchmark/run.py](benchmark/run.py):
- Confirm query ID resolution and repetition semantics for spatial.
- Add/verify seed handling and deterministic generation for each repeat.
- Ensure per-system timing arrays align 1:1 with generated query sequence.

Acceptance:
- Repeated runs with same seed produce same SQL/placeholder sequence.

### B3. CSV and metadata completeness
In [benchmark/writer.py](benchmark/writer.py) and runner path:
- Include benchmark name, query id, scale factor, system, snapshot, hostname.
- Add optional placeholders hash/seed columns for reproducibility.

Acceptance:
- CSV row can fully identify and replay a measured query.

---

## 6. Milestone C: Bespoke Spatial Path

### C1. Spatial query execution in generated engine
In the generated C++ pipeline under output template flow:
- Add parser support for spatial placeholders (point/radius/ids).
- Implement minimal spatial operators needed by benchmark queries.
- Start with correctness-first implementation, then optimize.

Acceptance:
- Bespoke executes all SpatialBench queries with valid outputs for at least one scale factor.

### C2. Validation parity with DuckDB
In validation flow:
- Add spatial-aware comparison policy.
- For floating-point outputs, define tolerance policy.
- For geometry-derived values, compare canonical scalar outputs (distance counts ids) before complex geometry text equality.

Acceptance:
- Validation pass rate is stable across repeated runs.

### C3. Optimization loop enablement
In [conversations/optimization_conversation.py](conversations/optimization_conversation.py) and prompt assets:
- Add spatial optimization prompt mode (or spatial branch of existing mode).
- Emphasize selective filtering order, bounding-box prefilter, memory locality, and candidate pruning.
- Keep same regression guardrails (revert on regressions).

Acceptance:
- Optimization conversation can run at least one full cycle on a spatial query.

### C4. Run scripts baseline IDs
In [run_optim_loop.py](run_optim_loop.py) and [run_gen_base_impl.py](run_gen_base_impl.py):
- Add configured spatial baseline IDs/snapshots once first good runs exist.
- Remove temporary fail-fast guard once IDs are available.

Acceptance:
- Spatial scripts work without manual source edits.

---

## 7. Milestone D: Hardening and Quality Gates

### D1. Tests
Add tests for:
- Query generation determinism and placeholder substitution.
- Query ID parsing for spatial benchmark names.
- Benchmark runner end-to-end duckdb-only smoke run.

Start with unit tests in existing test suite style.

Acceptance:
- New tests pass in CI/local.

### D2. Error handling and observability
- Standardize error messages for missing spatial data/functions.
- Add logging of generated SQL and placeholder map under debug mode.

Acceptance:
- Failures are diagnosable from logs without rerunning interactively.

### D3. Documentation and runbooks
Update:
- [README.md](README.md)
- [benchmark/README.md](benchmark/README.md)

Add:
- Data preparation steps for spatial benchmark.
- Known limitations and expected runtime profile.
- Repro command matrix (duckdb-only, bespoke-only, side-by-side).

Acceptance:
- A new contributor can run spatial benchmark by following docs only.

---

## 8. Execution Order (Recommended)
1. A1-A3 (freeze contracts)
2. B1-B3 (duckdb baseline path complete)
3. D1 minimal tests for generation/runner
4. C1-C2 (bespoke + validation parity)
5. C3-C4 (optimization integration + baseline IDs)
6. D2-D3 polish and docs

---

## 9. Risks and Mitigations
- Risk: Spatial function availability differs by DuckDB version.
  - Mitigation: startup capability check and pinned feature subset.
- Risk: Geometry equality is unstable for validation.
  - Mitigation: validate scalarized outputs and tolerance-based compares.
- Risk: Benchmark noise masks gains.
  - Mitigation: fixed seeds, warmup policy, repeat count, optional CPU pinning guidance.
- Risk: Scope creep into full GIS engine.
  - Mitigation: keep V1 query set small and measurable.

---

## 10. Definition of Done
SpatialBench is considered complete (V1) when:
- `--benchmark spatial` runs in benchmark CLI with DuckDB and Bespoke.
- Validation succeeds for full spatial query set at defined scale factors.
- Optimization loop can run spatial query improvements without manual patching.
- Reproducible CSV metrics and docs are in place.
- Core tests for generation, routing, and benchmark smoke path are passing.

---

## 11. Suggested First Work Package (Next 1-2 days)
- Finalize A1/A2 contracts.
- Implement B1 capability check + B2 deterministic repeat handling audit.
- Add D1 tests for spatial query generation and query-id routing.
- Run duckdb-only acceptance command and store first golden CSV.
