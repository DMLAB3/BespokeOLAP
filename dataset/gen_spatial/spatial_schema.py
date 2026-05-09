spatial_schema = """
Table: points
- point_id: BIGINT
- category: VARCHAR
- geom: GEOMETRY(POINT)

Table: regions
- region_id: INTEGER
- region_name: VARCHAR
- geom: GEOMETRY(POLYGON)
""".strip()
