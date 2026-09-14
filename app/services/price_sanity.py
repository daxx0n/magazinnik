"""Conservative checks that distinguish full prices from payment fragments."""

from __future__ import annotations

import math
import re
from collections.abc import Iterable
from statistics import median
from typing import TypeVar


_BYN_ALIASES = {"byn", "бел. руб.", "бел руб", "р", "руб"}
_IPHONE = re.compile(r"\biphone\b", re.IGNORECASE)
_DURABLE_GOODS = re.compile(
    r"\b(?:"
    r"смартфон|телефон|iphone|ноутбук|laptop|телевизор|"
    r"стиральн\w*\s+машин\w*|washing\s+machine|washer|"
    r"сушильн\w*\s+машин\w*|dryer|холодильник|refrigerator|"
    r"посудомоечн\w*\s+машин\w*|dishwasher|"
    r"духов\w*\s+шкаф\w*|oven|игров\w*\s+(?:консоль|приставк)\w*"
    r")\b",
    re.IGNORECASE,
)
_PAYMENT_FRAGMENT = re.compile(
    r"\b(?:в\s+месяц|ежемесячн\w*|плат[её]ж\w*|рассрочк\w*|"
    r"кредит\w*|\/\s*мес\.?|per\s+month|monthly)\b",
    re.IGNORECASE,
)

PriceItem = TypeVar("PriceItem")


def is_plausible_full_price(
    title: str,
    price: float,
    currency: str = "BYN",
    context: str | None = None,
) -> bool:
    """Reject values that cannot reasonably be a full new-product price."""

    try:
        numeric_price = float(price)
    except (TypeError, ValueError):
        return False
    if not math.isfinite(numeric_price) or numeric_price <= 0:
        return False

    normalized_currency = " ".join(currency.casefold().split())
    if context and _PAYMENT_FRAGMENT.search(context):
        return False
    if normalized_currency in _BYN_ALIASES and _IPHONE.search(title):
        # New iPhones in the catalog cannot have a full retail price close to
        # a monthly installment. Keep the floor deliberately far below even
        # old new-stock models to avoid filtering a legitimate promotion.
        return numeric_price >= 300
    if normalized_currency in _BYN_ALIASES and _DURABLE_GOODS.search(title):
        # This deliberately low boundary only catches deposits, instalments
        # and feed placeholders. It is not used to rank legitimate offers.
        return numeric_price >= 100
    return True


def filter_price_outliers(
    items: Iterable[PriceItem],
    *,
    ratio: float = 0.25,
) -> list[PriceItem]:
    """Rejects isolated payment fragments using the same-product cohort.

    Callers pass already model-matched offers. With at least two independent
    sellers/sources, a value below a quarter of the equally weighted source
    medians is not treated as a full price. This remains category-independent
    and leaves a lone source untouched so sparse catalogs keep working.
    """

    values: list[tuple[PriceItem, float]] = []
    for item in items:
        try:
            value = float(getattr(item, "price"))
        except (AttributeError, TypeError, ValueError):
            continue
        if math.isfinite(value) and value > 0:
            values.append((item, value))

    if len(values) < 2:
        return [item for item, _ in values]

    source_prices: dict[str, list[float]] = {}
    for item, value in values:
        source = str(
            getattr(item, "source", None)
            or getattr(item, "seller", None)
            or id(item)
        ).casefold()
        source_prices.setdefault(source, []).append(value)
    if len(source_prices) < 2:
        return [item for item, _ in values]

    # One marketplace can return dozens of rows for the same wrong payment.
    # Give every source one vote so it cannot outweigh other retailers.
    reference = median(
        median(prices) for prices in source_prices.values()
    )
    floor = reference * ratio
    return [item for item, value in values if value >= floor]
