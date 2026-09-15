"""Currency normalization helpers.

Historical spend is stored in both its source currency and USD.  The caller may
provide a dated FX rate for any currency.  USD and the two Gulf currencies with
official USD pegs used by this project have deterministic fallbacks.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Mapping


class FXRateMissing(ValueError):
    """Raised when a currency cannot be converted without inventing a rate."""


_PEGGED_TO_USD = {
    "USD": Decimal("1"),
    "SAR": Decimal("1") / Decimal("3.75"),
    "AED": Decimal("1") / Decimal("3.6725"),
}


def currency_code(value: str) -> str:
    """Return a validated ISO-style three-letter currency code."""
    code = (value or "").strip().upper()
    if len(code) != 3 or not code.isalpha():
        raise ValueError(f"Invalid currency code: {value!r}")
    return code


def rate_to_usd(
    currency: str,
    supplied_rates: Mapping[str, Decimal | float | str] | None = None,
) -> Decimal:
    """Return units of USD per one unit of ``currency``.

    ``supplied_rates`` must already represent the metric date.  This prevents a
    refresh from silently revaluing historical spend using today's rate.
    """
    code = currency_code(currency)
    if supplied_rates and code in supplied_rates:
        try:
            rate = Decimal(str(supplied_rates[code]))
        except InvalidOperation as exc:
            raise ValueError(f"Invalid {code} to USD rate") from exc
        if rate <= 0:
            raise ValueError(f"{code} to USD rate must be positive")
        return rate
    if code in _PEGGED_TO_USD:
        return _PEGGED_TO_USD[code]
    raise FXRateMissing(
        f"No dated {code} to USD rate supplied; refusing to estimate spend"
    )


def amount_to_usd(
    amount: Decimal | float | int | str,
    currency: str,
    supplied_rates: Mapping[str, Decimal | float | str] | None = None,
) -> tuple[Decimal, Decimal]:
    """Return ``(amount_usd, fx_to_usd)`` rounded for database storage."""
    source = Decimal(str(amount))
    if source < 0:
        raise ValueError("Spend cannot be negative")
    rate = rate_to_usd(currency, supplied_rates)
    return (source * rate).quantize(Decimal("0.000001")), rate.quantize(
        Decimal("0.0000000001")
    )

