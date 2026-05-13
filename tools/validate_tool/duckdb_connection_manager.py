import json
import os
import tempfile
from typing import Dict, Optional, Tuple

import duckdb
import pandas as pd
from tqdm import tqdm

from dataset.dataset_tables_dict import get_tables_for_benchmark


class DuckDBConnectionManager:
    def __init__(
        self,
        pre_load_duckdb_tables: bool,
        parquet_path: str,
        benchmark: str,
        sf: float = 1,
        pin_worker: bool = True,
        pin_core: Optional[int] = 3,
    ):
        self.con = None
        self.pre_load_duckdb_tables = pre_load_duckdb_tables
        self.parquet_path = parquet_path
        self.sf = sf
        self.pin_worker = pin_worker
        self.pin_core = pin_core
        self.benchmark = benchmark

        if self.pin_worker:
            assert self.pin_core is not None

        if pre_load_duckdb_tables:
            self.con = self.con_duckdb(parquet_path, benchmark=benchmark, sf=sf)

    def duckdb_sql(self, sql: str) -> Tuple[float, pd.DataFrame, Dict]:
        if not self.pre_load_duckdb_tables or self.con is None:
            self.con = self.con_duckdb(
                self.parquet_path, benchmark=self.benchmark, sf=self.sf
            )
        pid = 0  # 0 = current process
        orig_affinity = {}
        if self.pin_worker:
            orig_affinity = os.sched_getaffinity(pid)
            assert self.pin_core is not None
            os.sched_setaffinity(pid, {self.pin_core})  # pin to core 3

        # execute sql and get execution time and result dataframe
        with tempfile.NamedTemporaryFile(delete=True) as tmpfile:
            profile_output_path = tmpfile.name

            # Enable profiling and request JSON output
            self.con.execute("PRAGMA enable_profiling = 'json'")
            self.con.execute(f"PRAGMA profiling_output ='{profile_output_path}'")

            # Run query
            result_df = self.con.execute(sql).fetchdf()

            # Read and parse the profiling output
            with open(profile_output_path, "r") as f:
                profile_data = json.load(f)

            exec_time_ms = profile_data["latency"] * 1000.0  # convert to ms

        if self.pin_worker:
            os.sched_setaffinity(pid, orig_affinity)

        return exec_time_ms, result_df, profile_data

    def con_duckdb(
        self, parquet_path: str, benchmark: str, sf: float = 1
    ) -> duckdb.DuckDBPyConnection:
        # pre-load duckdb tables to warm up cache
        self.con = duckdb.connect(database=":memory:")
        if benchmark == "spatial":
            self._ensure_spatial_support(self.con)

        for table in tqdm(
            get_tables_for_benchmark(benchmark),
            desc=f"Loading DuckDB tables for SF{sf}",
        ):
            self.con.execute(
                f"CREATE TABLE {table} AS SELECT * FROM read_parquet('{parquet_path}/sf{sf}/{table}.parquet')"
            )

        if benchmark == "spatial":
            self._validate_spatial_data_contract(self.con)

        # disable parallelism in duckdb for more consistent benchmarking
        self.con.execute("PRAGMA threads=1;")

        return self.con

    def _ensure_spatial_support(self, con: duckdb.DuckDBPyConnection) -> None:
        try:
            con.execute("LOAD spatial")
        except Exception:
            try:
                con.execute("INSTALL spatial")
                con.execute("LOAD spatial")
            except Exception as exc:
                raise RuntimeError(
                    "DuckDB spatial extension is required for benchmark='spatial'. "
                    "Install/load it manually (INSTALL spatial; LOAD spatial) or use a DuckDB build that includes it."
                ) from exc

        # Verify required functions used by the DuckDB SpatialBench templates.
        checks = [
            "SELECT ST_AsText(ST_GeomFromText('POINT (0 0)'))",
            "SELECT ST_DWithin(ST_GeomFromText('POINT (0 0)'), ST_GeomFromText('POINT (1 1)'), 2)",
            "SELECT ST_Intersects(ST_GeomFromText('POINT (0 0)'), ST_GeomFromText('POINT (0 0)'))",
            "SELECT ST_Within(ST_GeomFromText('POINT (1 1)'), ST_GeomFromText('POLYGON((0 0,2 0,2 2,0 2,0 0))'))",
            "SELECT ST_Area(ST_GeomFromText('POLYGON((0 0,1 0,1 1,0 1,0 0))'))",
            "SELECT ST_Length(ST_MakeLine(ST_GeomFromText('POINT (0 0)'), ST_GeomFromText('POINT (1 1)')))",
        ]
        for stmt in checks:
            try:
                con.execute(stmt)
            except Exception as exc:
                raise RuntimeError(
                    "DuckDB spatial capability check failed. "
                    f"Statement failed: {stmt}"
                ) from exc

    def _validate_spatial_data_contract(self, con: duckdb.DuckDBPyConnection) -> None:
        required_cols = {
            "building": {"b_buildingkey", "b_name", "b_boundary"},
            "customer": {"c_custkey", "c_name"},
            "driver": {"d_driverkey"},
            "trip": {
                "t_tripkey",
                "t_custkey",
                "t_driverkey",
                "t_vehiclekey",
                "t_pickuptime",
                "t_dropofftime",
                "t_fare",
                "t_tip",
                "t_totalamount",
                "t_distance",
                "t_pickuploc",
                "t_dropoffloc",
            },
            "vehicle": {"v_vehiclekey"},
            "zone": {"z_zonekey", "z_name", "z_boundary"},
        }
        for table, expected_cols in required_cols.items():
            rows = con.execute(f"PRAGMA table_info('{table}')").fetchall()
            if not rows:
                raise RuntimeError(
                    f"Spatial data contract violation: missing table '{table}'."
                )
            actual_cols = {row[1] for row in rows}
            missing = expected_cols - actual_cols
            if missing:
                raise RuntimeError(
                    "Spatial data contract violation for table "
                    f"'{table}'. Missing columns: {sorted(missing)}"
                )

        geometry_checks = {
            "building": "b_boundary",
            "trip": "t_pickuploc",
            "zone": "z_boundary",
        }
        for table, column in geometry_checks.items():
            try:
                con.execute(
                    f"""
                    SELECT ST_AsText(ST_GeomFromWKB({column}))
                    FROM {table}
                    WHERE {column} IS NOT NULL
                    LIMIT 1
                    """
                ).fetchall()
            except Exception as exc:
                raise RuntimeError(
                    "Spatial data contract violation for table "
                    f"'{table}'. Column '{column}' must be binary WKB decodable "
                    "by DuckDB ST_GeomFromWKB."
                ) from exc

    def clear_mem_footprint(self) -> None:
        if self.con is not None:
            self.con.close()
            self.con = None
