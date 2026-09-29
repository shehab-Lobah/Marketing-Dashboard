from datetime import date
import unittest

from data_pipeline.sync_paid import rolling_window


class PaidSyncTests(unittest.TestCase):
    def test_rolling_window_is_inclusive(self) -> None:
        start, end = rolling_window(7, date(2026, 9, 13))
        self.assertEqual(start, date(2026, 9, 7))
        self.assertEqual(end, date(2026, 9, 13))

    def test_rejects_non_positive_window(self) -> None:
        with self.assertRaisesRegex(ValueError, "positive"):
            rolling_window(0, date(2026, 9, 13))


if __name__ == "__main__":
    unittest.main()

