# SpatialBench Contract (V1)

## Scope
SpatialBench V1 focuses on two deterministic query families:
- Q1: Point-in-polygon aggregation by region id.
- Q2: Radius search with distance ordering and top-k limit.

This contract defines query behavior, placeholders, data schema assumptions, and validation rules.

## Query Contract

### Q1: Region Containment Count
Intent:
- Count points contained in one selected region polygon.

Template semantics:
- Join points to regions through `ST_Contains(r.geom, p.geom)`.
- Restrict to one region id using placeholder `REGION_ID`.
- Output one row per matched region id.

Placeholders:
- `REGION_ID`: integer in [1, 32].

Output schema:
- `region_id` (integer)
- `point_count` (integer)

Determinism:
- Placeholder generation is seeded.
- Output ordering is deterministic due to grouped single key filter.

### Q2: Radius Search
Intent:
- Find nearest points to a query point within radius.

Template semantics:
- Filter with `ST_DWithin(p.geom, QUERY_POINT, RADIUS)`.
- Project distance `ST_Distance(p.geom, QUERY_POINT)`.
- Order by distance ascending.
- Return first `LIMIT_N` rows.

Placeholders:
- `QUERY_POINT`: SQL expression `ST_Point(<lon>, <lat>)`.
- `RADIUS`: float in [50.0, 1500.0].
- `LIMIT_N`: integer in [10, 200].

Output schema:
- `point_id` (integer)
- `category` (string)
- `dist` (float)

Determinism:
- Placeholder generation is seeded.
- Ties in distance should be considered implementation-defined unless explicitly secondary-sorted.

## Data Contract
Expected tables in parquet under `.../sf<SCALE_FACTOR>/`:

### points
- `point_id` BIGINT
- `category` VARCHAR
- `geom` GEOMETRY(POINT)

### regions
- `region_id` INTEGER
- `region_name` VARCHAR
- `geom` GEOMETRY(POLYGON)

Required runtime checks:
- Spatial extension loaded in DuckDB.
- Required functions available: `ST_Point`, `ST_DWithin`, `ST_Contains`.
- Required tables/columns exist.

## Metric Contract
For each measured query execution, CSV row must include:
- `query_id`
- `scale_factor`
- `benchmark`
- `system`
- `time_ms`
- `hostname`
- `snapshot`
- `seed`
- `placeholders_hash`

## Validation Rules (Initial)
- Correctness baseline: compare against DuckDB output.
- For floating-point `dist`: allow tolerance-based comparison in later bespoke validation extension.
- Prefer validating scalar outputs before introducing geometry text comparison.

## Versioning
- Contract version: `SpatialBench-V1`.
- Any template/schema/metric changes must update this file and changelog notes in benchmark docs.
