import random
from typing import Dict, Optional, Tuple

from dataset.gen_spatial.spatial_queries import spatial_templates


# Keep the search area near a realistic lat/lon window for deterministic synthetic workloads.
def _random_query_point(rnd: random.Random) -> str:
    lon = rnd.uniform(-122.55, -122.30)
    lat = rnd.uniform(37.68, 37.86)
    return f"ST_Point({lon:.6f}, {lat:.6f})"


def gen_query(
    query_name: str = "Q1", rnd: Optional[random.Random] = None, seed: int = 42
) -> Tuple[str, str, Dict[str, str]]:
    if query_name not in spatial_templates:
        raise KeyError(f"Unknown spatial query name: {query_name}")

    if rnd is None:
        rnd = random.Random(seed)

    placeholders: Dict[str, str] = {}

    if query_name == "Q1":
        placeholders["REGION_ID"] = str(rnd.randint(1, 32))
    elif query_name == "Q2":
        placeholders["QUERY_POINT"] = _random_query_point(rnd)
        placeholders["RADIUS"] = f"{rnd.uniform(50.0, 1500.0):.2f}"
        placeholders["LIMIT_N"] = str(rnd.randint(10, 200))
    else:
        raise ValueError(f"No placeholder generator defined for {query_name}")

    template = spatial_templates[query_name]
    query = template
    for key, value in placeholders.items():
        query = query.replace(f"[{key}]", value)

    return template, query, placeholders
