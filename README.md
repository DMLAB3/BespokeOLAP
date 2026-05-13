[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-Apache%202.0-g.svg)](LICENSE)
[![uv](https://img.shields.io/badge/dependency%20manager-uv-orange.svg)](https://github.com/astral-sh/uv)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Release](https://img.shields.io/badge/release-1.0-blue.svg)]()
[![Paper](https://img.shields.io/badge/paper-arXiv-red.svg)](https://arxiv.org/pdf/2603.02001)
# Bespoke-OLAP

Sourcecode of the paper *Bespoke OLAP: Synthesizing Workload-Specific One-size-fits-one Database Engines*

**Quick links:** &nbsp;
[📄 Paper](https://arxiv.org/pdf/2603.02001) &nbsp;·&nbsp;
[🌐 Webpage](https://datamanagementlab.github.io/BespokeOLAP/) &nbsp;·&nbsp;
[▶ Live Runner](https://datamanagementlab.github.io/BespokeOLAP/web-runner/)

The generated C++ artifacts of *Bespoke-TPCH* and *Bespoke-CEB* are available in the [BespokeOLAP_Artifacts](https://github.com/DataManagementLab/BespokeOLAP_Artifacts) repository.

An LLM agent that automatically generates and optimizes custom C++ OLAP query engines for user specified workloads. The agent generates C++ code, compiles it, and iteratively improves performance through sophisticated optimization loops. Results are tracked in Weights & Biases (wandb).

<div align="center">
    <figure>
        <img src="misc/bespoke_olap.jpg" alt="Bespoke OLAP architecture" width="600">
        <p><em>Bespoke OLAP: Synthesizing Workload-Specific Database Engines</em></p>
    </figure>
    <figure>
        <img src="misc/speedups.jpg" alt="Performance speedups" width="400">
        <p><em>Performance improvements across workloads</em></p>
    </figure>
</div>

Statistics of the generated engines and optimization runs can be found in this public [wandb project](https://wandb.ai/jwehrstein/BespokeOLAP).

---

## 🌐 Interactive Demo

> **[datamanagementlab.github.io/BespokeOLAP](https://datamanagementlab.github.io/BespokeOLAP/)**
>
> - **Synthesis explainer** — step-by-step walkthrough of what happened in each synthesis stage
> - **Live demo** — run the synthesized DBMS with custom query placeholders directly in the browser

---

## How It Works

1. **Storage plan generation** — the agent designs a custom data layout for the target workload
2. **Base implementation** — the agent generates a complete C++ engine (loader, builder, query executors)
3. **Optimization loop** — the agent iteratively improves performance, guided by speedup metrics and automatic validation against DuckDB reference results

The generated engine uses a hot-reload architecture: loader, builder, and query executors are compiled as shared libraries and reloaded without restarting the host process.

## Prerequisites

- Linux (x86-64)
- C++ toolchain (`gcc` / `clang`)
- Python 3.10+
- [`uv`](https://github.com/astral-sh/uv) package manager
- Apache Arrow and Parquet development libraries

## Installation

### 1. Install uv

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

*Optional:* Setup Weights & Biases (wandb) account and API key for experiment tracking. You can sign up for free at [https://wandb.ai/](https://wandb.ai/).

### 2. Install Arrow and Parquet libraries

```bash
wget https://packages.apache.org/artifactory/arrow/$(lsb_release --id --short | tr 'A-Z' 'a-z')/apache-arrow-apt-source-latest-$(lsb_release --codename --short).deb
sudo apt install -y -V ./apache-arrow-apt-source-latest-$(lsb_release --codename --short).deb
sudo apt update
sudo apt install -y libarrow-dev libparquet-dev parquet-tools
```

### 3. Install Python dependencies

```bash
uv sync
```

### 4. Configure environment

Create a `.env` file with your API keys:

```bash
GEMINI_API_KEY=...
WANDB_ENTITY=... # Optional, e.g. "my-team"
WANDB_PROJECT=... # Optional, e.g. "bespoke-olap"
```

### 5. Prepare Parquet data

Place TPC-H or CEB Parquet files in your artifacts directory (default: `/home/mk/`). The path can be overridden with `--base_parquet_dir`.

## Usage

### 1. Activate your Python environment

```bash
source .venv/bin/activate
```

### 2. Generate a storage plan for your workload
The conversation name resembles: `storageplan{q_id}-{q_id}v{version}`. For example, `storageplan1-22v1` is a storage plan generated for TPC-H queries 1 and 22, version 1.
```bash
# TPC-H
python run_gen_storage_plan.py \
    --conv storageplan1-22v1 \
    --benchmark tpch \
    --auto_u --auto_finish

# CEB
python run_gen_storage_plan.py \
    --conv storageplan1a-11bv1 \
    --benchmark ceb \
    --auto_u --auto_finish

# Spatial
uv run run_gen_storage_plan.py \
    --conv storageplan1-12v1 \
    --benchmark spatial \
    --auto_u --auto_finish
```
(Optional) `--auto_u` and `--auto_finish` flags can be used to automatically approve prompts and finish the conversation when no more prompts remain, enabling a fully automated run. Use with caution, as it will skip all user interactions.

### 3. Generate a base implementation

```bash
# TPC-H
python run_gen_base_impl.py \
    --conv basef1-22v1 \
    --benchmark tpch \
    --auto_u --auto_finish

# CEB
python run_gen_base_impl.py \
    --conv basef1a-11bv1 \
    --benchmark ceb \
    --auto_u --auto_finish

# Spatial
python run_gen_base_impl.py \
    --conv basef1-12v1 \
    --benchmark spatial \
    --auto_u --auto_finish
```
Conv name represents: `basef{q_id}-{q_id}v{version}`. For example, `basef1-22v1` is a base implementation generated for TPC-H queries 1 and 22, version 1.

Git snapshot handoff for storage plans is disabled in the DSPy runtime. To use a
generated storage plan for base implementation work, keep `storage_plan.txt` in
`./output/` and run manual/continue mode so the current workspace is preserved.

```bash
python main.py manual \
    --conv_name spatial_base_with_storage \
    --query_list 1,2 \
    --benchmark spatial \
    --continue_run
```

### 4. Run the optimization loop
The optimization loop now starts from the current `./output/` workspace. Generate
or place a baseline implementation there first; `run_optim_loop.py` no longer
looks up a W&B run-id and restores a git snapshot.

```bash
# TPC-H
python run_optim_loop.py \
    --conv runoptim1-22v1 \
    --bespoke_storage \
    --benchmark tpch \
    --auto_u --auto_finish

# CEB
python run_optim_loop.py \
    --conv runoptim1a-11bv1 \
    --bespoke_storage \
    --benchmark ceb \
    --auto_u --auto_finish
```

### Hint: Conversation Names
Conversation names are used to organize and track runs.
They first create separate log-files but also identify traces and metrics in wandb.
Further they reference the queries for which an engine is generated and optimized, as well as the version number for the generated engine.
Hence they have to be unique - this is also enforced by the system.
Usually naming conventions (conversation name prefixes) are enforced by the scripts.

## Optionally
### Run the agent manually (interactive)

```bash
python main.py manual \
    --conv_name <name> \
    --query_list <q_ids> \
    --benchmark tpch
```

### Benchmark a generated engine

```bash
python -m benchmark --systems bespoke,duckdb --scale_factors 1,5,20 --benchmark tpch
```

Experimental spatial benchmark:

```bash
python -m dataset.gen_spatial.generate_spatial_data \
  --scale-factor 0.001 \
  --output-root /home/mk/spatial_parquet \
  --compact \
  --overwrite
python -m benchmark --systems duckdb --scale_factors 0.001 --benchmark spatial
```

See [Benchmarking guide](benchmark/README.md) for details and additional examples.

## CLI Reference

Common arguments shared across entry points:
(We recommend using the prepared scripts above, which have the appropriate arguments pre-configured.)

| Argument                  | Default              | Description                                                                              |
|---------------------------|----------------------|------------------------------------------------------------------------------------------|
| `--benchmark`             | `tpch`               | Benchmark to use (`tpch`, `ceb`, or experimental `spatial`).                             |
| `--conv` / `--conv_name`  | *(required)*         | Conversation name (auto-prefixed with benchmark name).                                   |
| `--model`                 | `gemini/gemini-3.1-flash-lite` | DSPy/LiteLLM model ID to use.                                                      |
| `--artifacts_dir`         | `/home/mk/...`  | Directory for caches, conversations, and Parquet data. Local run logs are written under `./output/logs/`. |
| `--base_parquet_dir`      | *(artifacts_dir)*    | Base directory for Parquet files.                                                        |
| `--replay`                | `False`              | Replay a prior run strictly from cache (fails on cache miss).                            |
| `--replay_cache`          | `False`              | Reuse cached prompts; auto-advance until the first uncached LLM call.                   |
| `--auto_u`                | `False`              | Auto-approve all prompts without user interaction. Use with caution.                     |
| `--auto_finish`           | `False`              | Automatically finish when no more prompts remain in the conversation. Otherwise the user can continue prompting manually.                   |
| `--notify`                | `False`              | Send a notification when the conversation requires user input.                           |
| `--disable_wandb`         | `False`              | Skip wandb logging.                                                                      |
| `--disable_valtool`       | `False`              | Disable automatic validation after each compile+run.                                     |
| `--continue_run`          | `False`              | Continue from the current `./output` state instead of cleaning and copying a fresh template. |

The agent runtime is DSPy-based and uses Gemini directly by default. You can
override the model with any DSPy/LiteLLM model name:

```bash
GEMINI_API_KEY=... python run_gen_storage_plan.py \
    --conv storageplan1-22v1 \
    --benchmark tpch \
    --model gemini/gemini-3.1-flash-lite \
    --auto_u --auto_finish
```

## Architecture

### Agent Loop (`main.py`)

The core orchestrator. It drives a DSPy ReAct agent with four tools:

- **`apply_patch`** — edits files in `./output/`
- **`shell`** — runs shell commands in `./output/`
- **`compile`** — compiles the C++ engine in `./output/build/`
- **`run`** — compiles, runs queries, and validates results against DuckDB

When W&B is enabled, the DSPy runtime also installs a native DSPy callback that
logs module, LM, and tool start/end events to the active W&B run.
Full local LLM request/response records are written as JSONL under
`./output/logs/*_llm_calls.jsonl`.

### Conversation Modes (`conversations/`)

- **`ScriptedConversation`** — plays through a JSON list of pre-written prompts; the user can interject or replace prompts interactively
- **`OptimizationConversation`** — self-steering loop that reads speedup metrics and decides when to continue, revert, or stop

Accepted prompts are persisted to a JSON file in `artifacts_dir/conversations/` so runs can be replayed exactly.

### C++ Engine Template (`misc/fasttest/`)

The template and host process for the generated OLAP engine. The agent generates and modifies:

- `loader_impl.{cpp,hpp}` — loads Parquet data into `ParquetTables`
- `builder_impl.{cpp,hpp}` — transforms `ParquetTables` into a custom `Database` layout
- `query_impl.{cpp,hpp}` — executes individual queries against `Database`
- `db.cpp` — host process; detects `.so` changes and hot-reloads without restarting

### Caching System (`llm_cache/`)

Multi-layer caching for reproducibility:

- **LLM cache** — hashes requests and stores/replays responses from disk
- **Shell cache** — caches shell command outputs when a snapshotter is available; disabled on the active no-snapshot DSPy runtime path
- **DSPy session store** — persists compacted context summaries and recent turns

To clear caches, delete the relevant subdirectories under `artifacts_dir/cache/`.

### Validation (`tools/validate_tool/`)

`QueryValidator` runs the generated engine at multiple scale factors and compares results against DuckDB. Invoked automatically by `run_tool` after each compile+run.

### Benchmarking (`benchmark/`)

Separate from the agent loop. See [benchmark/README.md](benchmark/README.md).

### Spatial Optimization (Experimental)

Spatial support is scaffolded to unblock spatial-query experiments while keeping the current TPC-H/CEB workflow stable.

- Query templates: `dataset/gen_spatial/spatial_queries.py`
- Query instantiation: `dataset/gen_spatial/gen_spatial_query.py`
- Data generation: `dataset/gen_spatial/generate_spatial_data.py` for local Python-generated data; official `spatialbench-cli` for full-fidelity benchmark data
- Schema metadata: `dataset/gen_spatial/spatial_schema.py`
- Benchmark query set: `benchmark/run.py` (`Q1` through `Q12`)

Recommended optimization focus for spatial workloads:

1. Add geometry-aware filtering early (bounding-box reject before exact predicates).
2. Reorder joins to maximize spatial selectivity first.
3. Separate storage of geometry payloads from frequently filtered scalar attributes.
4. Add per-query timing and trace counters for predicate selectivity and candidate set sizes.

Current limitations:

- `run_optim_loop.py` requires a baseline implementation already present in `./output/`.
- Git snapshot handoff is disabled in the DSPy runtime; `run_gen_base_impl.py --with_storage_plan`, `--start_snapshot`, and `--storage_plan_snapshot` are not supported.

## Development

### Inspect running engine processes

```bash
watch -n1 -d ./misc/get_db_procs.sh
```

### Query Parquet files with DuckDB

```bash
duckdb :memory:
```

```sql
.timer on
PRAGMA threads=1;

CREATE TABLE orders   AS SELECT * FROM read_parquet('orders.parquet');
CREATE TABLE lineitem AS SELECT * FROM read_parquet('lineitem.parquet');
-- ... add other tables as needed
```
