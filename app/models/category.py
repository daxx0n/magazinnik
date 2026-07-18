from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProductCategory:
    """Раздел каталога, найденный для широкого запроса."""

    key: str
    title: str
