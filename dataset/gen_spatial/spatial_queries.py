spatial_templates = {
    "Q1": """
SELECT
    r.region_id,
    COUNT(*) AS point_count
FROM points p
JOIN regions r
    ON ST_Contains(r.geom, p.geom)
WHERE r.region_id = [REGION_ID]
GROUP BY r.region_id;
""".strip(),
    "Q2": """
SELECT
    p.point_id,
    p.category,
    ST_Distance(p.geom, [QUERY_POINT]) AS dist
FROM points p
WHERE ST_DWithin(p.geom, [QUERY_POINT], [RADIUS])
ORDER BY dist
LIMIT [LIMIT_N];
""".strip(),
}
