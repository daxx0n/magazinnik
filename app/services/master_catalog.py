from dataclasses import replace

from app.models.catalog import (
    ExternalCatalogItem,
    MasterCatalogProduct,
    MatchLevel,
)
from app.services.product_matcher import ProductMatcher


class MasterCatalog:
    """In-memory мастер-каталог с идемпотентным upsert офферов."""

    def __init__(self, matcher: ProductMatcher | None = None) -> None:
        self._matcher = matcher or ProductMatcher()
        self._products: dict[str, MasterCatalogProduct] = {}
        self._external_index: dict[tuple[str, str], str] = {}
        self._sequence = 0

    @property
    def products(self) -> tuple[MasterCatalogProduct, ...]:
        return tuple(self._products.values())

    def upsert(self, item: ExternalCatalogItem) -> MasterCatalogProduct:
        """Добавляет или обновляет внешний товар без создания дублей."""

        external_key = (item.source.casefold(), item.external_id)
        existing_product_key = self._external_index.get(external_key)

        if existing_product_key is not None:
            product = self._products[existing_product_key]
            self._replace_offer(product, item)
            return product

        matched_product = self._find_match(item)
        if matched_product is None:
            matched_product = self._create_product(item)
        else:
            matched_product.offers.append(item)

        self._external_index[external_key] = matched_product.key
        return matched_product

    def search(self, query: str) -> list[MasterCatalogProduct]:
        """Ищет по мастер-названию и исходным названиям офферов."""

        normalized_query = " ".join(query.casefold().split())
        if not normalized_query:
            return []

        scored: list[tuple[int, MasterCatalogProduct]] = []
        for product in self._products.values():
            searchable_values = [product.title, *(offer.title for offer in product.offers)]
            score = max(
                self._search_score(normalized_query, value.casefold())
                for value in searchable_values
            )
            if score:
                scored.append((score, product))

        scored.sort(key=lambda pair: (-pair[0], pair[1].title.casefold()))
        return [product for _, product in scored]

    def _find_match(self, item: ExternalCatalogItem) -> MasterCatalogProduct | None:
        if item.identity is None:
            return None

        best: tuple[float, MasterCatalogProduct] | None = None
        for product in self._products.values():
            result = self._matcher.match(product.identity, item.identity)
            if result.level not in {MatchLevel.EXACT, MatchLevel.PROBABLE}:
                continue
            if best is None or result.score > best[0]:
                best = (result.score, product)

        return best[1] if best is not None else None

    def _create_product(self, item: ExternalCatalogItem) -> MasterCatalogProduct:
        if item.identity is None:
            raise ValueError("identity is required for a new master product")

        self._sequence += 1
        product = MasterCatalogProduct(
            key=f"product-{self._sequence}",
            title=item.title,
            identity=item.identity,
            offers=[item],
        )
        self._products[product.key] = product
        return product

    @staticmethod
    def _replace_offer(
        product: MasterCatalogProduct,
        item: ExternalCatalogItem,
    ) -> None:
        for index, existing in enumerate(product.offers):
            if (
                existing.source.casefold() == item.source.casefold()
                and existing.external_id == item.external_id
            ):
                product.offers[index] = replace(item)
                return
        product.offers.append(item)

    @staticmethod
    def _search_score(query: str, value: str) -> int:
        if query == value:
            return 3
        if value.startswith(query):
            return 2
        if query in value:
            return 1
        return 0
