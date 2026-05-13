import random
import unittest

from benchmark.run import get_all_query_ids
from dataset.gen_spatial.gen_spatial_query import gen_query
from dataset.query_gen_factory import get_placeholders_fn, get_query_gen
from utils.gen_common import parse_query_ids


class TestSpatialBenchScaffold(unittest.TestCase):
    def test_get_all_query_ids_spatial(self):
        self.assertEqual(get_all_query_ids("spatial"), [str(i) for i in range(1, 13)])

    def test_parse_query_ids_spatial_range(self):
        qids = parse_query_ids("storageplan1-12v1", "storageplan", benchmark="spatial")
        self.assertEqual(qids, [str(i) for i in range(1, 13)])

    def test_spatial_gen_query_deterministic(self):
        rnd1 = random.Random(123)
        rnd2 = random.Random(123)

        t1, q1, p1 = gen_query(query_name="Q12", rnd=rnd1)
        t2, q2, p2 = gen_query(query_name="Q12", rnd=rnd2)

        self.assertEqual(t1, t2)
        self.assertEqual(q1, q2)
        self.assertEqual(p1, p2)
        self.assertIn("CROSS JOIN LATERAL", q1)
        self.assertEqual(p1, {})

    def test_factory_supports_spatial(self):
        gen_fn = get_query_gen("spatial")
        _, q, placeholders = gen_fn(query_name="Q1", rnd=random.Random(7))
        self.assertIn("ST_DWithin", q)
        self.assertIn("trip", q)
        self.assertEqual(placeholders, {})

    def test_placeholders_fn_supports_spatial(self):
        placeholders_fn = get_placeholders_fn("spatial")
        placeholders = placeholders_fn(query_name="Q2", rnd=random.Random(99))
        self.assertEqual(placeholders, {})


if __name__ == "__main__":
    unittest.main()
