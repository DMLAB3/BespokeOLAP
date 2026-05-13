"""DuckDB SQL templates adapted from Apache Sedona SpatialBench.

Source: https://github.com/apache/sedona-spatialbench/blob/main/spatialbench-queries/print_queries.py
The upstream benchmark defines fixed queries, not randomized templates, so these
strings intentionally have no placeholders.
"""

spatial_templates = {
    "Q1": """
-- Q1: Find trips starting within 50km of Sedona city center, ordered by distance
SELECT
   t.t_tripkey, ST_X(ST_GeomFromWKB(t.t_pickuploc)) AS pickup_lon, ST_Y(ST_GeomFromWKB(t.t_pickuploc)) AS pickup_lat, t.t_pickuptime,
   ST_Distance(ST_GeomFromWKB(t.t_pickuploc), ST_GeomFromText('POINT (-111.7610 34.8697)')) AS distance_to_center
FROM trip t
WHERE ST_DWithin(ST_GeomFromWKB(t.t_pickuploc), ST_GeomFromText('POINT (-111.7610 34.8697)'), 0.45)
ORDER BY distance_to_center ASC, t.t_tripkey ASC
""".strip(),
    "Q2": """
-- Q2: Count trips starting within Coconino County (Arizona) zone
SELECT COUNT(*) AS trip_count_in_coconino_county
FROM trip t
WHERE ST_Intersects(ST_GeomFromWKB(t.t_pickuploc), (SELECT ST_GeomFromWKB(z.z_boundary) FROM zone z WHERE z.z_name = 'Coconino County' LIMIT 1))
""".strip(),
    "Q3": """
-- Q3: Monthly trip statistics within 15km radius of Sedona city center (10km base + 5km buffer)
SELECT
   DATE_TRUNC('month', t.t_pickuptime) AS pickup_month, COUNT(t.t_tripkey) AS total_trips,
   AVG(t.t_distance) AS avg_distance, AVG(t.t_dropofftime - t.t_pickuptime) AS avg_duration,
   AVG(t.t_fare) AS avg_fare
FROM trip t
WHERE ST_DWithin(
             ST_GeomFromWKB(t.t_pickuploc),
             ST_GeomFromText('POLYGON((-111.9060 34.7347, -111.6160 34.7347, -111.6160 35.0047, -111.9060 35.0047, -111.9060 34.7347))'),
             0.045
     )
GROUP BY pickup_month
ORDER BY pickup_month
""".strip(),
    "Q4": """
-- Q4: Zone distribution of top 1000 trips by tip amount
SELECT z.z_zonekey, z.z_name, COUNT(*) AS trip_count
FROM
   zone z
       JOIN (
       SELECT t.t_pickuploc
       FROM trip t
       ORDER BY t.t_tip DESC, t.t_tripkey ASC
           LIMIT 1000
   ) top_trips ON ST_Within(ST_GeomFromWKB(top_trips.t_pickuploc), ST_GeomFromWKB(z.z_boundary))
GROUP BY z.z_zonekey, z.z_name
ORDER BY trip_count DESC, z.z_zonekey ASC
""".strip(),
    "Q5": """
-- Q5: Monthly travel patterns for repeat customers (convex hull of dropoff locations)
SELECT
   c.c_custkey, c.c_name AS customer_name,
   DATE_TRUNC('month', t.t_pickuptime) AS pickup_month,
   ST_Area(ST_ConvexHull(ST_Collect(ARRAY_AGG(ST_GeomFromWKB(t.t_dropoffloc))))) AS monthly_travel_hull_area,
   COUNT(*) as dropoff_count
FROM trip t JOIN customer c ON t.t_custkey = c.c_custkey
GROUP BY c.c_custkey, c.c_name, pickup_month
HAVING dropoff_count > 5
ORDER BY dropoff_count DESC, c.c_custkey ASC
""".strip(),
    "Q6": """
-- Q6: Zone statistics for trips intersecting a bounding box
SELECT
   z.z_zonekey, z.z_name,
   COUNT(t.t_tripkey) AS total_pickups, AVG(t.t_totalamount) AS avg_distance,
   AVG(t.t_dropofftime - t.t_pickuptime) AS avg_duration
FROM trip t, zone z
WHERE ST_Intersects(ST_GeomFromText('POLYGON((-112.2110 34.4197, -111.3110 34.4197, -111.3110 35.3197, -112.2110 35.3197, -112.2110 34.4197))'), ST_GeomFromWKB(z.z_boundary))
 AND ST_Within(ST_GeomFromWKB(t.t_pickuploc), ST_GeomFromWKB(z.z_boundary))
GROUP BY z.z_zonekey, z.z_name
ORDER BY total_pickups DESC, z.z_zonekey ASC
""".strip(),
    "Q7": """
-- Q7: Detect potential route detours by comparing reported vs. geometric distances
WITH trip_lengths AS (
   SELECT
       t.t_tripkey,
       t.t_distance AS reported_distance_m,
       ST_Length(
               ST_MakeLine(
                       ST_GeomFromWKB(t.t_pickuploc),
                       ST_GeomFromWKB(t.t_dropoffloc)
               )
       ) / 0.000009 AS line_distance_m
   FROM trip t
)
SELECT
   t.t_tripkey,
   t.reported_distance_m,
   t.line_distance_m,
   t.reported_distance_m / NULLIF(t.line_distance_m, 0) AS detour_ratio
FROM trip_lengths t
ORDER BY detour_ratio DESC NULLS LAST, reported_distance_m DESC, t_tripkey ASC
""".strip(),
    "Q8": """
-- Q8: Count nearby pickups for each building within 500m radius
SELECT b.b_buildingkey, b.b_name, COUNT(*) AS nearby_pickup_count
FROM trip t JOIN building b ON ST_DWithin(ST_GeomFromWKB(t.t_pickuploc), ST_GeomFromWKB(b.b_boundary), 0.0045)
GROUP BY b.b_buildingkey, b.b_name
ORDER BY nearby_pickup_count DESC, b.b_buildingkey ASC
""".strip(),
    "Q9": """
-- Q9: Building Conflation (duplicate/overlap detection via IoU), deterministic order
WITH b1 AS (
   SELECT b_buildingkey AS id, ST_GeomFromWKB(b_boundary) AS geom
   FROM building
),
    b2 AS (
        SELECT b_buildingkey AS id, ST_GeomFromWKB(b_boundary) AS geom
        FROM building
    ),
    pairs AS (
        SELECT
            b1.id AS building_1,
            b2.id AS building_2,
            ST_Area(b1.geom) AS area1,
            ST_Area(b2.geom) AS area2,
            ST_Area(ST_Intersection(b1.geom, b2.geom)) AS overlap_area
        FROM b1
                 JOIN b2
                      ON b1.id < b2.id
                          AND ST_Intersects(b1.geom, b2.geom)
    )
SELECT
   building_1,
   building_2,
   area1,
   area2,
   overlap_area,
   CASE
       WHEN overlap_area = 0 THEN 0.0
       WHEN (area1 + area2 - overlap_area) = 0 THEN 1.0
       ELSE overlap_area / (area1 + area2 - overlap_area)
       END AS iou
FROM pairs
ORDER BY iou DESC, building_1 ASC, building_2 ASC
""".strip(),
    "Q10": """
-- Q10: Zone statistics for trips starting within each zone
SELECT
   z.z_zonekey, z.z_name AS pickup_zone, AVG(t.t_dropofftime - t.t_pickuptime) AS avg_duration,
   AVG(t.t_distance) AS avg_distance, COUNT(t.t_tripkey) AS num_trips
FROM zone z LEFT JOIN trip t ON ST_Within(ST_GeomFromWKB(t.t_pickuploc), ST_GeomFromWKB(z.z_boundary))
GROUP BY z.z_zonekey, z.z_name
ORDER BY avg_duration DESC NULLS LAST, z.z_zonekey ASC
""".strip(),
    "Q11": """
-- Q11: Count trips that cross between different zones
SELECT COUNT(*) AS cross_zone_trip_count
FROM
   trip t
       JOIN zone pickup_zone ON ST_Within(ST_GeomFromWKB(t.t_pickuploc), ST_GeomFromWKB(pickup_zone.z_boundary))
       JOIN zone dropoff_zone ON ST_Within(ST_GeomFromWKB(t.t_dropoffloc), ST_GeomFromWKB(dropoff_zone.z_boundary))
WHERE pickup_zone.z_zonekey != dropoff_zone.z_zonekey
""".strip(),
    "Q12": """
-- Q12 (DuckDB): No KNN join, using cross join lateral instead.
SELECT
   t.t_tripkey,
   t.t_pickuploc,
   nb.b_buildingkey,
   nb.building_name,
   nb.distance_to_building
FROM trip t
        CROSS JOIN LATERAL (
   SELECT
       b.b_buildingkey,
       b.b_name AS building_name,
       ST_Distance(ST_GeomFromWKB(t.t_pickuploc), ST_GeomFromWKB(b.b_boundary)) AS distance_to_building
   FROM building b
   ORDER BY distance_to_building
       LIMIT 5
) AS nb
ORDER BY nb.distance_to_building, nb.b_buildingkey
""".strip(),
}
