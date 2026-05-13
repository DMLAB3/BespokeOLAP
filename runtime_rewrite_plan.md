# Runtime Rewrite Plan (Fast Path)

Date: 2026-05-13
Branch: rewrite/e2e-architecture-2026-05-13

## Locked Decisions

1. Scope: runtime only (no benchmark/dataset rewrites beyond runtime touch points).
2. CLI compatibility: no strict backward compatibility requirement (breaking runtime internals and command shape is acceptable).
3. Execution strategy: fastest path to clean architecture.
4. Validation: full test coverage gate for completion (run full suite, not smoke only).
5. Baseline: include current dirty working tree changes as part of rewrite baseline.

## Objective

Replace the current runtime orchestration with a modular architecture that keeps behavior (generation + optimization workflows) while removing large-file coupling and reducing side-effect-heavy wiring in `main.py` and `llm_cache/dspy_runtime.py`.

## Current Runtime Surface

- Entry and orchestration: `main.py`
- Workflow wrappers: `run_gen_storage_plan.py`, `run_gen_base_impl.py`, `run_optim_loop.py`
- Runtime core and tool adapters: `llm_cache/dspy_runtime.py`
- Conversation engine: `conversations/conversation.py`, `conversations/optimization_conversation.py`
- Workspace edits: `tools/workspace_editor.py`
- Config builder: `utils/cli_config.py`

## Target Runtime Architecture

New package root: `runtime/`

- `runtime/config/`
- `runtime/bootstrap/`
- `runtime/orchestrator/`
- `runtime/agent/`
- `runtime/conversation/`
- `runtime/services/`
- `runtime/adapters/`

### Module Responsibilities

- `runtime/config`: typed runtime settings and argument translation.
- `runtime/bootstrap`: environment checks, logging, tracing, wandb init, workspace prep.
- `runtime/orchestrator`: top-level run flow and dependency wiring.
- `runtime/agent`: DSPy runner split into callbacks, cache/session store, and model execution.
- `runtime/conversation`: conversation lifecycle hooks and mode dispatch.
- `runtime/services`: workflow services (storage plan generation, base implementation, optimization loop run setup).
- `runtime/adapters`: wrappers for compile/run/apply-patch/shell/workspace editor contracts.

## Fast-Path Migration Order

### Phase 1: Skeleton + Stable Contracts

Deliverables:
- Create `runtime/` package structure.
- Add shared protocol/typing contracts for runtime dependencies.
- Add an orchestrator shell callable from `main.py`.

Exit criteria:
- Existing commands still execute through thin adapters.
- No behavior change expected yet.

### Phase 2: Main Orchestration Split

Deliverables:
- Move workspace preparation and tool wiring from `main.py` into `runtime/bootstrap` and `runtime/orchestrator`.
- Keep `main.py` as minimal CLI boundary.

Exit criteria:
- `main.py` is primarily argument handling and single orchestration call.
- Existing unit tests still pass.

### Phase 3: DSPy Runtime Decomposition

Deliverables:
- Split `llm_cache/dspy_runtime.py` into:
  - callbacks/logging
  - cache/session store
  - toolbox and tool wrappers
  - agent run logic
- Keep import compatibility only where needed during cutover.

Exit criteria:
- Functionality preserved, large monolith reduced.
- Runtime-specific tests updated and passing.

### Phase 4: Conversation and Wrapper Alignment

Deliverables:
- Route wrapper scripts through runtime services (`runtime/services`).
- Normalize mode dispatch (`scripted`, `optimization`) behind orchestrator.

Exit criteria:
- Wrapper scripts are thin and declarative.
- Runtime flow location is obvious and centralized.

### Phase 5: Cleanup + Full Test Gate

Deliverables:
- Remove dead compatibility shims no longer needed.
- Update docs for new runtime boundaries.

Exit criteria:
- Full test suite passes.
- `python -m compileall main.py` passes.
- No unresolved TODOs introduced by rewrite.

## Full Test Gate

Run after each phase where code moves materially:

```bash
uv run pytest
uv run python -m compileall main.py
```

If phase-level failures appear, fix immediately before continuing.

## Risk Controls

- Keep old files functional until equivalent new modules are wired.
- Move code in small vertical slices (wiring + tests together).
- Avoid changing benchmark/query generation logic unless required by runtime boundaries.

## Definition of Done

- Runtime modules live under `runtime/` with clear responsibilities.
- `main.py` is slim and delegates orchestration.
- `llm_cache/dspy_runtime.py` no longer acts as a monolith.
- Wrapper scripts become declarative service invocations.
- Full test suite passes on rewrite branch.
