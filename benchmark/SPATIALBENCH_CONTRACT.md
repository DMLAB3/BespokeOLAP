# SpatialBench Contract (V1)

## Scope
SpatialBench V1 adapts the 12 fixed SQL queries from Apache Sedona SpatialBench
for DuckDB. The workload covers point radius search, zone containment,
bounding-box filtering, spatial joins, route-distance analysis, building
proximity, overlap/conflation, and nearest-building lookup.

This contract defines query behavior, placeholders, data schema assumptions, and validation rules.

## Query Contract

### Queries
- Q1: trips starting within 50km of Sedona city center.
- Q2: trips starting within Coconino County.
- Q3: monthly trip statistics near Sedona.
- Q4: zone distribution for top-tip trips.
- Q5: repeat-customer monthly dropoff convex hulls.
- Q6: zone statistics for trips intersecting a bounding box.
- Q7: reported route distance vs. geometric line distance.
- Q8: nearby pickups per building.
- Q9: building overlap/conflation by IoU.
- Q10: zone statistics for trip pickups.
- Q11: cross-zone trip count.
- Q12: five nearest buildings to each trip pickup using DuckDB lateral join.

Placeholders:
- None. Upstream SpatialBench defines fixed benchmark statements.

Determinism:
- Queries include deterministic `ORDER BY` clauses where row ordering matters.
- Seeds are still accepted by local generator APIs for compatibility but do not
  change SQL text.

## Data Contract
Expected tables in parquet under `.../sf<SCALE_FACTOR>/`. Real benchmark data
should be generated with Apache SpatialBench `spatialbench-cli`:

```bash
spatialbench-cli --scale-factor 1 --format=parquet --output-dir .../spatial_parquet/sf1
```

### trip
- `t_tripkey`, `t_custkey`, `t_driverkey`, `t_vehiclekey`
- `t_pickuptime`, `t_dropofftime`
- `t_fare`, `t_tip`, `t_totalamount`, `t_distance`
- `t_pickuploc`, `t_dropoffloc` as WKB point payloads

### customer
- `c_custkey`, `c_name`

### driver
- `d_driverkey`
- Note: SpatialBench docs list driver abbreviation as `s_`, while the upstream
  parquet schema emits `d_` driver columns.

### vehicle
- `v_vehiclekey`

### zone
- `z_zonekey`, `z_name`, `z_boundary` as WKB polygon/multipolygon payload

### building
- `b_buildingkey`, `b_name`, `b_boundary` as WKB polygon payload

### Cardinality
- `trip`: `6M x SF`
- `customer`: `30K x SF`
- `driver`: `500 x SF`
- `vehicle`: `100 x SF`
- `building`: `20K x (1 + log2(SF))`
- `zone`: tiered by SF (`156,095` below SF10, then `455,711`,
  `1,035,371`, and `1,035,749` for the larger documented tiers)

Required runtime checks:
- Spatial extension loaded in DuckDB.
- Required functions available for the adapted query set, including `ST_GeomFromWKB`, `ST_GeomFromText`, `ST_DWithin`, `ST_Intersects`, `ST_Within`, `ST_Distance`, `ST_Area`, `ST_Intersection`, `ST_MakeLine`, and `ST_Length`.
- Required tables/columns exist.
- Geometry payload columns remain parquet binary/WKB and must decode through
  `ST_GeomFromWKB`.

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
