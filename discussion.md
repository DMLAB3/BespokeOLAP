# Correctness Checking for Generated Code
- I am thinking to add fuzzing 

Generated C++ code is checked for correctness through the `run_tool` and
`QueryValidator` validation path. The check is automatic unless validation is
explicitly disabled with `--disable_valtool` or by the conversation validation
toggle.

The validation flow is:

1. `run_tool` compiles the generated engine. A compile failure immediately marks
   validation as failed with `validation/compile_error=True`.
2. `QueryValidator` pre-generates query instantiations for the configured query
   ids and scale factors.
3. The same instantiated SQL queries are executed in DuckDB, which is treated as
   the reference implementation. DuckDB results, runtimes, and query metadata are
   cached.
4. The generated engine is run on the same query ids and placeholder arguments.
   It must print timing lines in the form `<RUN_NR> | Execution ms: <num>` and
   write each query result as `result<RUN_NR>.csv`.
5. The validator parses stdout and checks that the number of timing lines
   matches the number of expected query instantiations.
6. For every query result, the generated CSV is loaded with pandas and compared
   against the cached DuckDB dataframe.

The result comparison checks:

- the expected `result<RUN_NR>.csv` file exists;
- the CSV can be parsed;
- the output column set matches DuckDB's output column set;
- row contents match DuckDB under set semantics, so row order is ignored unless
  the SQL query has an `ORDER BY`;
- floating point comparisons use a tolerance of `atol=1e-2` and `rtol=1e-2`;
- if the query has `ORDER BY`, the ordered columns are compared separately to
  ensure the ordering constraint is respected.

If any check fails, validation returns an error message containing the query id,
placeholder values, SQL text, DuckDB output, implementation output, and the
pandas assertion error when applicable. If all checks pass, validation records
`validation/correct=True` and reports DuckDB runtime, generated implementation
runtime, and per-query speedup metrics.

# How Generated Code Is Patched

Patch generation and correctness checking are separate stages. The model first
proposes code changes through an `apply_patch` tool; only after those changes are
applied does the system compile and validate the generated engine.

The generated engine starts from the `misc/fasttest/` template copied into
`./output`. The model normally patches files such as:

- `loader_impl.cpp` / `loader_impl.hpp`, for loading Parquet data;
- `builder_impl.cpp` / `builder_impl.hpp`, for building the specialized
  in-memory `Database` layout;
- `query_impl.cpp` / `query_impl.hpp`, for query-specific execution logic;
- occasionally `db.cpp` or helper headers when the runtime interface changes.

Patch application is handled by `WorkspaceEditor`. It supports three operations:

- `create_file`, which creates a new file from added diff lines;
- `update_file`, which reads the existing file, applies the supplied diff, and
  writes the patched result back;
- `delete_file`, which removes a file.

The editor resolves paths relative to `./output` and rejects operations outside
that generated-code workspace. In the current implementation, edited files must
also live directly in the workspace root rather than in subdirectories, which
keeps generated changes scoped to the copied engine files.

For OpenAI Responses models, the built-in `ApplyPatchTool` is connected to
`WorkspaceEditor`. For LiteLLM models, `tools/litellm_apply_patch.py` exposes a
compatible `apply_patch` function tool. That wrapper normalizes unified diffs by
removing headers such as `diff --git`, `index`, `---`, and `+++`; for file
creation, it keeps only added lines before passing the diff to `WorkspaceEditor`.

After a patch is applied, the model calls the compile tool or the run tool. The
run tool automatically compiles first. Compilation is cached using a hash that
includes the current generated-code snapshot and compiler flags. Validation
results are cached separately using the generated-code snapshot, query ids,
scale factor, validation mode, timeout, compile key, repetitions, and other run
configuration.

The end-to-end loop is:

1. the model proposes a patch through `apply_patch`;
2. `WorkspaceEditor` applies the patch inside `./output`;
3. the compile/run tools build and execute the patched generated engine;
4. `QueryValidator` compares the generated CSV outputs against DuckDB.

The patch itself is therefore not proof of correctness. It is only the proposed
code change; correctness is established later by compilation and DuckDB-based
output comparison.

# Why Patch Instead of Regenerate

Patches are used because, after the initial implementation exists, the generated
engine is a working codebase rather than a blank target. Most later changes are
localized fixes, query implementations, instrumentation edits, or performance
optimizations. Applying a small patch preserves unrelated working code and makes
the validation result easier to interpret.

This has several practical benefits:

- it keeps the blast radius small when fixing a correctness bug;
- it avoids accidentally breaking interfaces such as query argument parsing,
  timing output, CSV naming, and generated result format;
- it makes performance changes easier to measure because each validation run is
  tied to a concrete diff;
- it reduces context and token cost because the model does not need to rewrite
  all generated files on every iteration;
- it works naturally with git snapshots, compile caching, validation caching,
  and rollback after regressions.

The tradeoff is that the current loop mostly follows one patch trajectory at a
time. It does not generate many independent patch variants, benchmark all of
them, and select the best candidate. A more guided and measured platform could
potentially work better: for example, one that asks the model for several
candidate patches, applies each on an isolated branch or snapshot, runs the same
compile/validation/benchmark suite, and keeps the best correct variant. That
would cost more compute and orchestration, but it could explore the optimization
space more effectively than a single incremental patch path.
