from __future__ import annotations

import argparse
import math
from pathlib import Path

import duckdb


def _sf_dir_name(scale_factor: float) -> str:
    return f"sf{scale_factor:g}"


def _ensure_spatial(con: duckdb.DuckDBPyConnection) -> None:
    try:
        con.execute("LOAD spatial")
    except Exception:
        con.execute("INSTALL spatial")
        con.execute("LOAD spatial")


def _copy_table(con: duckdb.DuckDBPyConnection, table: str, output_dir: Path) -> None:
    path = (output_dir / f"{table}.parquet").as_posix().replace("'", "''")
    con.execute(f"COPY {table} TO '{path}' (FORMAT PARQUET)")


def _spatialbench_building_rows(scale_factor: float) -> int:
    if scale_factor < 1:
        return 0
    return max(0, int(20_000 * (1 + math.log2(scale_factor))))


def _spatialbench_zone_rows(scale_factor: float) -> int:
    if scale_factor < 10:
        return 156_095
    if scale_factor < 100:
        return 455_711
    if scale_factor < 1000:
        return 1_035_371
    return 1_035_749


def _polygon_wkb_expr(lon: str, lat: str, half_size: float) -> str:
    hs = f"{half_size:.8f}"
    return f"""
        CAST(ST_AsWKB(
            ST_GeomFromText(
                'POLYGON((' ||
                ({lon} - {hs})::VARCHAR || ' ' || ({lat} - {hs})::VARCHAR || ',' ||
                ({lon} + {hs})::VARCHAR || ' ' || ({lat} - {hs})::VARCHAR || ',' ||
                ({lon} + {hs})::VARCHAR || ' ' || ({lat} + {hs})::VARCHAR || ',' ||
                ({lon} - {hs})::VARCHAR || ' ' || ({lat} + {hs})::VARCHAR || ',' ||
                ({lon} - {hs})::VARCHAR || ' ' || ({lat} - {hs})::VARCHAR || '))'
            )
        ) AS BLOB)
    """


def generate_spatial_data(
    output_root: Path,
    scale_factor: float,
    seed: int = 42,
    overwrite: bool = False,
    compact: bool = False,
) -> Path:
    """Generate a compact SpatialBench-compatible parquet dataset.

    Geometry payloads are written as WKB `BLOB`/parquet binary columns. The query
    templates decode them with DuckDB's `ST_GeomFromWKB`, matching the upstream
    SpatialBench parquet contract.

    By default, table cardinalities follow the published SpatialBench data
    model. Use `compact=True` for a tiny local smoke dataset. Use Apache
    SpatialBench's `spatialbench-cli` for full-fidelity geometry distributions.
    """

    if scale_factor <= 0:
        raise ValueError("scale_factor must be positive")

    output_dir = output_root / _sf_dir_name(scale_factor)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not overwrite and any(output_dir.glob("*.parquet")):
        raise FileExistsError(
            f"{output_dir} already contains parquet files. Use --overwrite to replace them."
        )

    trip_rows = max(1, int(6_000_000 * scale_factor))
    customer_rows = max(1, int(30_000 * scale_factor))
    driver_rows = max(1, int(500 * scale_factor))
    vehicle_rows = max(1, int(100 * scale_factor))
    building_rows = _spatialbench_building_rows(scale_factor)
    zone_rows = _spatialbench_zone_rows(scale_factor)

    if compact:
        trip_rows = min(trip_rows, 6_000)
        customer_rows = min(customer_rows, 30)
        driver_rows = min(driver_rows, 1)
        vehicle_rows = min(vehicle_rows, 1)
        building_rows = max(16, min(max(building_rows, 16), 200))
        zone_rows = min(zone_rows, 64)

    con = duckdb.connect(database=":memory:")
    _ensure_spatial(con)
    con.execute("PRAGMA threads=1")

    con.execute(
        """
        CREATE TABLE customer AS
        SELECT
            i::BIGINT AS c_custkey,
            'Customer ' || i::VARCHAR AS c_name,
            'Address ' || i::VARCHAR AS c_address,
            CASE i % 4 WHEN 0 THEN 'AMERICA' WHEN 1 THEN 'EUROPE' WHEN 2 THEN 'ASIA' ELSE 'AFRICA' END AS c_region,
            'Nation ' || (i % 32)::VARCHAR AS c_nation,
            '+1-555-' || lpad((i % 10000)::VARCHAR, 4, '0') AS c_phone
        FROM range(1, ? + 1) AS r(i)
        """,
        [customer_rows],
    )

    con.execute(
        """
        CREATE TABLE driver AS
        SELECT
            i::BIGINT AS d_driverkey,
            'Driver ' || i::VARCHAR AS d_name,
            'Driver Address ' || i::VARCHAR AS d_address,
            CASE i % 4 WHEN 0 THEN 'AMERICA' WHEN 1 THEN 'EUROPE' WHEN 2 THEN 'ASIA' ELSE 'AFRICA' END AS d_region,
            'Nation ' || (i % 32)::VARCHAR AS d_nation,
            '+1-555-' || lpad((9000 + i % 1000)::VARCHAR, 4, '0') AS d_phone
        FROM range(1, ? + 1) AS r(i)
        """,
        [driver_rows],
    )

    con.execute(
        """
        CREATE TABLE vehicle AS
        SELECT
            i::BIGINT AS v_vehiclekey,
            'MFGR#' || (i % 5)::VARCHAR AS v_mfgr,
            'Brand#' || (i % 20)::VARCHAR AS v_brand,
            CASE i % 3 WHEN 0 THEN 'sedan' WHEN 1 THEN 'van' ELSE 'truck' END AS v_type,
            'synthetic spatialbench vehicle' AS v_comment
        FROM range(1, ? + 1) AS r(i)
        """,
        [vehicle_rows],
    )

    con.execute(
        f"""
        CREATE TABLE zone AS
        WITH coords AS (
            SELECT
                i,
                -112.05 + ((i - 1) % 8) * 0.08 AS lon,
                34.65 + floor((i - 1) / 8) * 0.08 AS lat
            FROM range(1, ? + 1) AS r(i)
        )
        SELECT
            i::BIGINT AS z_zonekey,
            'GERS-' || i::VARCHAR AS z_gersid,
            'US' AS z_country,
            'Arizona' AS z_region,
            CASE WHEN i = 1 THEN 'Coconino County' ELSE 'Synthetic Zone ' || i::VARCHAR END AS z_name,
            CASE WHEN i = 1 THEN 'county' ELSE 'microhood' END AS z_subtype,
            CASE
                WHEN i = 1 THEN CAST(ST_AsWKB(ST_GeomFromText('POLYGON((-112.6 34.1, -111.0 34.1, -111.0 35.7, -112.6 35.7, -112.6 34.1))')) AS BLOB)
                ELSE {_polygon_wkb_expr("lon", "lat", 0.06)}
            END AS z_boundary
        FROM coords
        """,
        [zone_rows],
    )

    con.execute(
        f"""
        CREATE TABLE building AS
        WITH coords AS (
            SELECT
                i,
                -112.05 + ((i * 37 + {seed}) % 1000) / 1000.0 * 0.60 AS lon,
                34.55 + ((i * 53 + {seed}) % 1000) / 1000.0 * 0.60 AS lat
            FROM range(1, ? + 1) AS r(i)
        )
        SELECT
            i::BIGINT AS b_buildingkey,
            'Building ' || i::VARCHAR AS b_name,
            {_polygon_wkb_expr("lon", "lat", 0.0015)} AS b_boundary
        FROM coords
        """,
        [building_rows],
    )

    con.execute(
        """
        CREATE TABLE trip AS
        WITH coords AS (
            SELECT
                i,
                -112.05 + ((i * 17 + ?) % 1000) / 1000.0 * 0.60 AS pickup_lon,
                34.55 + ((i * 29 + ?) % 1000) / 1000.0 * 0.60 AS pickup_lat,
                -112.05 + ((i * 31 + ?) % 1000) / 1000.0 * 0.60 AS dropoff_lon,
                34.55 + ((i * 43 + ?) % 1000) / 1000.0 * 0.60 AS dropoff_lat
            FROM range(1, ? + 1) AS r(i)
        )
        SELECT
            i::BIGINT AS t_tripkey,
            ((i - 1) % ?)::BIGINT + 1 AS t_custkey,
            ((i - 1) % ?)::BIGINT + 1 AS t_driverkey,
            ((i - 1) % ?)::BIGINT + 1 AS t_vehiclekey,
            (TIMESTAMP '1995-01-01' + ((i % 1576800)::BIGINT || ' minutes')::INTERVAL) AS t_pickuptime,
            (TIMESTAMP '1995-01-01' + (((i % 1576800) + 5 + (i % 120))::BIGINT || ' minutes')::INTERVAL) AS t_dropofftime,
            CAST(5 + (i % 5000) / 100.0 AS DECIMAL(15, 5)) AS t_fare,
            CAST((i % 1000) / 100.0 AS DECIMAL(15, 5)) AS t_tip,
            CAST(5 + (i % 5000) / 100.0 + (i % 1000) / 100.0 AS DECIMAL(15, 5)) AS t_totalamount,
            CAST(greatest(
                sqrt(pow(dropoff_lon - pickup_lon, 2) + pow(dropoff_lat - pickup_lat, 2)) / 0.000009,
                1.0
            ) AS DECIMAL(15, 5)) AS t_distance,
            CAST(ST_AsWKB(ST_Point(pickup_lon, pickup_lat)) AS BLOB) AS t_pickuploc,
            CAST(ST_AsWKB(ST_Point(dropoff_lon, dropoff_lat)) AS BLOB) AS t_dropoffloc
        FROM coords
        """,
        [seed, seed + 1, seed + 2, seed + 3, trip_rows, customer_rows, driver_rows, vehicle_rows],
    )

    for table in ["building", "customer", "driver", "trip", "vehicle", "zone"]:
        _copy_table(con, table, output_dir)

    con.close()
    return output_dir


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate synthetic SpatialBench parquet data.")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("/home/mk/spatial_parquet"),
        help="Directory that will contain sf<SCALE> subdirectories.",
    )
    parser.add_argument("--scale-factor", type=float, default=0.01)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Cap table sizes for quick local smoke tests.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    output_dir = generate_spatial_data(
        output_root=args.output_root,
        scale_factor=args.scale_factor,
        seed=args.seed,
        overwrite=args.overwrite,
        compact=args.compact,
    )
    print(output_dir.as_posix())


if __name__ == "__main__":
    main()
