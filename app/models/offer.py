from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProductOffer:
    """Предложение товара от одного магазина."""

    source: str
    title: str
    price: float
    currency: str
    available: bool
    url: str

    seller: str | None = None
    availability_text: str | None = None
    delivery_text: str | None = None
    updated_at: str | None = None