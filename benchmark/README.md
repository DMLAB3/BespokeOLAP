# Benchmarking

Benchmark execution is implemented in `benchmark/` and can be run directly as a module:

```bash
python -m benchmark --systems bespoke,duckdb --snapshots <hash1,hash2,...> --scale_factors 1,5,20 --benchmark tpch
```

## Common Commands

Run only Bespoke for selected query IDs:

```bash
python -m benchmark --systems bespoke --snapshots <hash> --scale_factors 1 --query_ids 1,2 --benchmark tpch
```

Run only DuckDB (no snapshots required):

```bash
python -m benchmark --systems duckdb --scale_factors 1,5,20 --benchmark tpch
```

Run experimental spatial benchmark (DuckDB only):

```bash
python -m dataset.gen_spatial.generate_spatial_data \
  --scale-factor 0.001 \
  --output-root /home/mk/spatial_parquet \
  --compact \
  --overwrite
python -m benchmark --systems duckdb --scale_factors 0.001 --benchmark spatial
```

Run with fixed seed for exact placeholder reproducibility:

```bash
python -m benchmark --systems duckdb --scale_factors 1 --benchmark spatial --seed 42 --csv benchmark/spatialbench_golden.csv
```

Append benchmark timings to CSV:

```bash
python -m benchmark --systems bespoke,duckdb --snapshots <hash> --scale_factors 1,5,20 --csv tpch.csv --benchmark tpch
```

## Notes

- `--snapshots` is required only when `bespoke` is included in `--systems`.
- Query IDs are resolved from benchmark definitions (`tpch`, `ceb`, or `spatial`), not from snapshot files.
- Spatial benchmark uses the 12 DuckDB SQL templates adapted from Apache Sedona SpatialBench in `dataset/gen_spatial/spatial_queries.py`.
- Spatial geometry columns are generated as parquet binary/WKB and decoded in SQL with `ST_GeomFromWKB`.
- `dataset.gen_spatial.generate_spatial_data` can generate local Python data. Use `--compact` for smoke tests; omit it to follow published table cardinalities. Use Apache SpatialBench `spatialbench-cli` for full-fidelity geometry distributions.
- Spatial contract (query/data/metrics): `benchmark/SPATIALBENCH_CONTRACT.md`.
