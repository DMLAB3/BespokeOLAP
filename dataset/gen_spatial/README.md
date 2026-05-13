# Spatial Data Generation

This repo includes a Python spatial data generator:

```bash
uv run -m dataset.gen_spatial.generate_spatial_data \
  --scale-factor 0.5 \
  --output-root /tmp/spatial_parquet \
  --overwrite
```

This writes parquet files to `/tmp/spatial_parquet/sf0.001/`. The `--compact`
flag caps table sizes for quick local smoke tests. Omit `--compact` to use the
published SpatialBench cardinality formulas for the requested scale factor:

```bash
python -m dataset.gen_spatial.generate_spatial_data \
  --scale-factor 1 \
  --output-root /home/mk/spatial_parquet \
  --overwrite
```

Use Apache SpatialBench's Rust generator when you need full-fidelity benchmark
geometry distributions:

```bash
git clone https://github.com/apache/sedona-spatialbench.git
cd sedona-spatialbench
cargo install --path spatialbench-cli
spatialbench-cli --scale-factor 1 --format=parquet --output-dir /home/mk/spatial_parquet/sf1
```

The generated parquet directory must contain:

- `building.parquet`
- `customer.parquet`
- `driver.parquet`
- `trip.parquet`
- `vehicle.parquet`
- `zone.parquet`

Spatial columns are stored as parquet binary/WKB payloads:

- `trip.t_pickuploc`
- `trip.t_dropoffloc`
- `building.b_boundary`
- `zone.z_boundary`

Queries decode these payloads with DuckDB `ST_GeomFromWKB(...)`; do not convert
the parquet columns to DuckDB `GEOMETRY` before writing.

## Data Model

| Table | Type | Abbr. | Primary Role | Spatial Attributes | Size per Scale Factor |
| --- | --- | --- | --- | --- | --- |
| `building` | Dimension | `b_` | Building footprints | Polygon footprints | `20K x (1 + log2(SF))` |
| `customer` | Dimension | `c_` | Trip customers | None | `30K x SF` |
| `driver` | Dimension | `s_` in docs, `d_` in parquet schema | Trip drivers | None | `500 x SF` |
| `trip` | Fact | `t_` | Trips, fare, distance, timestamps | Pickup/dropoff points | `6M x SF` |
| `vehicle` | Dimension | `v_` | Vehicles | None | `100 x SF` |
| `zone` | Dimension | `z_` | City zones | Polygon boundaries | Tiered by SF |

Zone cardinality follows SpatialBench's published tiers:

| Scale Factor | Zone Cardinality |
| --- | ---: |
| `[0, 10)` | `156,095` |
| `[10, 100)` | `455,711` |
| `[100, 1000)` | `1,035,371` |
| `[1000+)` | `1,035,749` |

Note: the SpatialBench docs list Driver abbreviation as `s_`, but the upstream
Arrow/parquet schema currently emits `d_driverkey`, `d_name`, `d_address`,
`d_region`, `d_nation`, and `d_phone`. This repo validates the generated parquet
schema, so it uses the `d_` column names.

Run the benchmark against Python-generated smoke data:

```bash
python -m dataset.gen_spatial.generate_spatial_data \
  --scale-factor 0.001 \
  --output-root /tmp/spatial_parquet \
  --compact \
  --overwrite
python -m benchmark --systems duckdb --scale_factors 0.001 --benchmark spatial --artifacts_dir /tmp
```

The benchmark expects data at `<artifacts_dir>/spatial_parquet/sf<SF>/`, so the
example above uses `--artifacts_dir /tmp`.
