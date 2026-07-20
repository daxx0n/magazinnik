from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class CatalogFeedIssue:
    """Ошибка одной записи товарного фида."""

    record: int
    field: str
    message: str


@dataclass(frozen=True, slots=True)
class CatalogFeedImportReport:
    """Результат валидации, dry-run или импорта."""

    status: str
    dry_run: bool
    total_records: int
    valid_records: int
    invalid_records: int
    created_products: int = 0
    merged_offers: int = 0
    updated_offers: int = 0
    product_keys: tuple[str, ...] = ()
    issues: tuple[CatalogFeedIssue, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
