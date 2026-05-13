from typing import Dict, Optional, Tuple

from dataset.gen_spatial.spatial_queries import spatial_templates


def gen_query(
    query_name: str = "Q1", rnd: Optional[object] = None, seed: int = 42
) -> Tuple[str, str, Dict[str, str]]:
    if query_name not in spatial_templates:
        raise KeyError(f"Unknown spatial query name: {query_name}")

    template = spatial_templates[query_name]
    return template, template, {}
