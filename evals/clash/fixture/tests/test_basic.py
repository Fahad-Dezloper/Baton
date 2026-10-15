import unittest

from shop import api, utils


class BasicTests(unittest.TestCase):
    def test_create_and_fetch(self):
        api.create_order("t1", [{"sku": "a", "price_cents": 250, "qty": 2}])
        got = api.fetch_order("t1")
        self.assertEqual(got["total_cents"], 500)

    def test_missing_order(self):
        self.assertIsNone(api.fetch_order("does-not-exist"))

    def test_clamp(self):
        self.assertEqual(utils.clamp(15, 0, 10), 10)


if __name__ == "__main__":
    unittest.main()
