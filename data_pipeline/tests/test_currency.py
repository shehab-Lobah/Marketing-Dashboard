from decimal import Decimal
import unittest

from data_pipeline.currency import FXRateMissing, amount_to_usd, rate_to_usd


class CurrencyTests(unittest.TestCase):
    def test_usd_is_unchanged(self) -> None:
        amount, rate = amount_to_usd("125.50", "usd")
        self.assertEqual(amount, Decimal("125.500000"))
        self.assertEqual(rate, Decimal("1.0000000000"))

    def test_sar_uses_official_peg(self) -> None:
        amount, _ = amount_to_usd("375", "SAR")
        self.assertEqual(amount, Decimal("100.000000"))

    def test_supplied_historical_rate_wins(self) -> None:
        self.assertEqual(rate_to_usd("EUR", {"EUR": "1.08"}), Decimal("1.08"))

    def test_unknown_currency_needs_a_dated_rate(self) -> None:
        with self.assertRaises(FXRateMissing):
            amount_to_usd("50", "EUR")


if __name__ == "__main__":
    unittest.main()
