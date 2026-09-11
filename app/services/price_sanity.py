"""Conservative checks that distinguish full prices from payment fragments."""

from __future__ import annotations

import math
import re


_BYN_ALIASES = {"byn", "бел. руб.", "бел руб", "р", "руб"}
_IPHONE = re.compile(r"\biphone\b", re.IGNORECASE)


def is_plausible_full_price(
    title: str,
    price: float,
    currency: str = "BYN",
) -> bool:
    """Reject values that cannot reasonably be a full new-product price."""

    try:
        numeric_price = float(price)
    except (TypeError, ValueError):
        return False
    if not math.isfinite(numeric_price) or numeric_price <= 0:
        return False

    normalized_currency = " ".join(currency.casefold().split())
    if normalized_currency in _BYN_ALIASES and _IPHONE.search(title):
        # New iPhones in the catalog cannot have a full retail price close to
        # a monthly installment. Keep the floor deliberately far below even
        # old new-stock models to avoid filtering a legitimate promotion.
        return numeric_price >= 300
    return True
