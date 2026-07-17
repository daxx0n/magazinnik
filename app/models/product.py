from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProductCandidate:
    """Карточка товара, найденная в каталоге."""

    key: str
    title: str
    url: str