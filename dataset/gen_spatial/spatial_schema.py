spatial_schema = """
Table: trip
- t_tripkey: BIGINT
- t_custkey: BIGINT
- t_driverkey: BIGINT
- t_vehiclekey: BIGINT
- t_pickuptime: TIMESTAMP
- t_dropofftime: TIMESTAMP
- t_fare: DOUBLE
- t_tip: DOUBLE
- t_totalamount: DOUBLE
- t_distance: DOUBLE
- t_pickuploc: WKB BINARY POINT
- t_dropoffloc: WKB BINARY POINT

Table: customer
- c_custkey: BIGINT
- c_name: VARCHAR

Table: driver
- d_driverkey: BIGINT

Table: vehicle
- v_vehiclekey: BIGINT

Table: zone
- z_zonekey: BIGINT
- z_name: VARCHAR
- z_boundary: WKB BINARY POLYGON/MULTIPOLYGON

Table: building
- b_buildingkey: BIGINT
- b_name: VARCHAR
- b_boundary: WKB BINARY POLYGON
""".strip()
