from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CatalogMetrics:
    """Накопленные метрики импорта и чтения мастер-каталога."""

    batches: int = 0
    total_offers: int = 0
    created_products: int = 0
    merged_offers: int = 0
    updated_offers: int = 0
    single_product_batches: int = 0
    ambiguous_batches: int = 0
    empty_batches: int = 0
    lookup_hits: int = 0
    lookup_misses: int = 0

    @property
    def duplicate_rate(self) -> float:
        """Доля офферов, привязанных к уже существующим карточкам."""

        if self.total_offers == 0:
            return 0.0
        return (
            self.merged_offers + self.updated_offers
        ) / self.total_offers

    @property
    def presentation_eligibility_rate(self) -> float:
        """Доля непустых пакетов, сопоставленных с одной карточкой."""

        non_empty_batches = self.batches - self.empty_batches
        if non_empty_batches == 0:
            return 0.0
        return self.single_product_batches / non_empty_batches
