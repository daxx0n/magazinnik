import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from app.models.catalog import (
    CatalogSnapshotMetrics,
    CatalogUpsertAction,
    CatalogUpsertResult,
    ExternalCatalogItem,
    MasterCatalogProduct,
    MatchLevel,
    MatchResult,
    MatchReview,
)
from app.services.product_matcher import ProductMatcher


class MasterCatalog:
    """In-memory мастер-каталог с идемпотентным upsert офферов."""

    _generated_key_pattern = re.compile(r"^product-(\d+)$")

    def __init__(self, matcher: ProductMatcher | None = None) -> None:
        self._matcher = matcher or ProductMatcher()
        self._products: dict[str, MasterCatalogProduct] = {}
        self._external_index: dict[tuple[str, str], str] = {}
        self._sequence = 0

    @property
    def products(self) -> tuple[MasterCatalogProduct, ...]:
        return tuple(self._products.values())

    @property
    def offer_count(self) -> int:
        return sum(len(product.offers) for product in self._products.values())

    def restore(self, products: Iterable[MasterCatalogProduct]) -> None:
        """Восстанавливает карточки, внешний индекс и генератор ключей."""

        restored_products: dict[str, MasterCatalogProduct] = {}
        restored_index: dict[tuple[str, str], str] = {}
        restored_sequence = 0

        for product in products:
            if product.key in restored_products:
                raise ValueError(f"Duplicate catalog product key: {product.key}")

            restored_products[product.key] = product
            key_match = self._generated_key_pattern.fullmatch(product.key)
            if key_match is not None:
                restored_sequence = max(
                    restored_sequence,
                    int(key_match.group(1)),
                )

            for offer in product.offers:
                external_key = self._external_key(offer)
                existing_product_key = restored_index.get(external_key)
                if (
                    existing_product_key is not None
                    and existing_product_key != product.key
                ):
                    raise ValueError(
                        "External offer belongs to multiple products: "
                        f"{external_key!r}"
                    )
                restored_index[external_key] = product.key

        self._products = restored_products
        self._external_index = restored_index
        self._sequence = restored_sequence

    def upsert(self, item: ExternalCatalogItem) -> MasterCatalogProduct:
        """Добавляет или обновляет внешний товар без создания дублей."""

        return self.upsert_with_result(item).product

    def upsert_with_result(
        self,
        item: ExternalCatalogItem,
    ) -> CatalogUpsertResult:
        """Выполняет upsert и возвращает тип произведённого изменения."""

        external_key = self._external_key(item)
        existing_product_key = self._external_index.get(external_key)

        if existing_product_key is not None:
            product = self._products[existing_product_key]
            self._replace_offer(product, item)
            return CatalogUpsertResult(
                product=product,
                action=CatalogUpsertAction.UPDATED,
            )

        best_match = self._best_match(item)
        matched_product: MasterCatalogProduct | None = None

        if best_match is not None:
            candidate_product, match_result = best_match
            item = self._with_match_metadata(
                item,
                match_result,
                candidate_product.key,
            )
            if match_result.level in {
                MatchLevel.EXACT,
                MatchLevel.PROBABLE,
            }:
                matched_product = candidate_product

        if matched_product is None:
            if best_match is None:
                item = replace(item, match_reason="new_product")
            matched_product = self._create_product(item)
            action = CatalogUpsertAction.CREATED
        else:
            matched_product.offers.append(item)
            action = CatalogUpsertAction.MERGED

        self._external_index[external_key] = matched_product.key
        return CatalogUpsertResult(
            product=matched_product,
            action=action,
        )

    def search(self, query: str) -> list[MasterCatalogProduct]:
        """Ищет по мастер-названию и исходным названиям офферов."""

        normalized_query = " ".join(query.casefold().split())
        if not normalized_query:
            return []

        scored: list[tuple[int, MasterCatalogProduct]] = []
        for product in self._products.values():
            searchable_values = [
                product.title,
                *(offer.title for offer in product.offers),
            ]
            score = max(
                self._search_score(normalized_query, value.casefold())
                for value in searchable_values
            )
            if score:
                scored.append((score, product))

        scored.sort(
            key=lambda pair: (-pair[0], pair[1].title.casefold())
        )
        return [product for _, product in scored]

    def pending_reviews(self, limit: int = 20) -> tuple[MatchReview, ...]:
        """Возвращает последние спорные совпадения из snapshot каталога."""

        reviews: list[MatchReview] = []
        for product in self._products.values():
            for offer in product.offers:
                if (
                    offer.match_level != MatchLevel.REVIEW
                    or offer.match_candidate_key is None
                    or offer.match_score is None
                    or offer.match_reason is None
                ):
                    continue

                candidate = self._products.get(offer.match_candidate_key)
                if candidate is None:
                    continue

                reviews.append(
                    MatchReview(
                        product_key=product.key,
                        product_title=product.title,
                        candidate_product_key=candidate.key,
                        candidate_product_title=candidate.title,
                        source=offer.source,
                        external_id=offer.external_id,
                        incoming_title=offer.title,
                        score=offer.match_score,
                        reason=offer.match_reason,
                        conflicts=offer.match_conflicts,
                        created_at=offer.updated_at,
                    )
                )

        reviews.sort(key=lambda review: review.created_at, reverse=True)
        return tuple(reviews[: max(limit, 0)])

    def accept_review(
        self,
        product_key: str,
        candidate_product_key: str,
    ) -> MasterCatalogProduct:
        """Объединяет спорную карточку с подтверждённым кандидатом."""

        if product_key == candidate_product_key:
            raise ValueError("Review product and candidate must differ")

        product = self._require_product(product_key)
        candidate = self._require_product(candidate_product_key)
        self._require_review_pair(product, candidate_product_key)

        for offer in tuple(product.offers):
            approved_offer = replace(
                offer,
                match_level=MatchLevel.PROBABLE,
                match_reason="manual_approval",
                match_candidate_key=candidate.key,
            )
            self._replace_offer(candidate, approved_offer)
            self._external_index[
                self._external_key(approved_offer)
            ] = candidate.key

        self._products.pop(product.key)
        return candidate

    def reject_review(
        self,
        product_key: str,
        candidate_product_key: str,
    ) -> MasterCatalogProduct:
        """Фиксирует, что спорные карточки являются разными товарами."""

        product = self._require_product(product_key)
        self._require_product(candidate_product_key)
        review_indexes = self._require_review_pair(
            product,
            candidate_product_key,
        )

        for index in review_indexes:
            product.offers[index] = replace(
                product.offers[index],
                match_level=MatchLevel.REJECTED,
                match_reason="manual_rejection",
            )
        return product

    def metrics(
        self,
        now: datetime | None = None,
        stale_after: timedelta = timedelta(hours=24),
    ) -> CatalogSnapshotMetrics:
        """Считает дедупликацию, качество матчей и свежесть офферов."""

        reference_time = self._aware_datetime(
            now or datetime.now(timezone.utc)
        )
        freshness_threshold = reference_time - stale_after
        product_count = len(self._products)
        offer_count = self.offer_count
        merged_offer_count = max(offer_count - product_count, 0)
        source_counts: Counter[str] = Counter()
        match_counts: Counter[MatchLevel] = Counter()
        single_source_products = 0
        multi_source_products = 0
        fresh_offers = 0
        stale_offers = 0
        unavailable_offers = 0

        for product in self._products.values():
            product_sources = {
                offer.source.strip().casefold()
                for offer in product.offers
                if offer.source.strip()
            }
            if len(product_sources) > 1:
                multi_source_products += 1
            else:
                single_source_products += 1

            for offer in product.offers:
                source_counts[offer.source.strip() or "unknown"] += 1
                if offer.match_level is not None:
                    match_counts[offer.match_level] += 1
                if not offer.available:
                    unavailable_offers += 1

                if self._aware_datetime(offer.updated_at) >= freshness_threshold:
                    fresh_offers += 1
                else:
                    stale_offers += 1

        duplicate_rate = (
            merged_offer_count / offer_count
            if offer_count
            else 0.0
        )
        return CatalogSnapshotMetrics(
            product_count=product_count,
            offer_count=offer_count,
            merged_offer_count=merged_offer_count,
            duplicate_rate=duplicate_rate,
            single_source_products=single_source_products,
            multi_source_products=multi_source_products,
            exact_matches=match_counts[MatchLevel.EXACT],
            probable_matches=match_counts[MatchLevel.PROBABLE],
            review_matches=match_counts[MatchLevel.REVIEW],
            rejected_matches=match_counts[MatchLevel.REJECTED],
            fresh_offers=fresh_offers,
            stale_offers=stale_offers,
            unavailable_offers=unavailable_offers,
            source_offer_counts=tuple(
                sorted(
                    source_counts.items(),
                    key=lambda item: (-item[1], item[0].casefold()),
                )
            ),
        )

    def _best_match(
        self,
        item: ExternalCatalogItem,
    ) -> tuple[MasterCatalogProduct, MatchResult] | None:
        if item.identity is None:
            return None

        best: tuple[MasterCatalogProduct, MatchResult] | None = None
        for product in self._products.values():
            result = self._matcher.match(product.identity, item.identity)
            if best is None or result.score > best[1].score:
                best = (product, result)
        return best

    def _create_product(
        self,
        item: ExternalCatalogItem,
    ) -> MasterCatalogProduct:
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

    def _require_product(self, product_key: str) -> MasterCatalogProduct:
        product = self._products.get(product_key)
        if product is None:
            raise ValueError(f"Unknown catalog product: {product_key}")
        return product

    @staticmethod
    def _require_review_pair(
        product: MasterCatalogProduct,
        candidate_product_key: str,
    ) -> tuple[int, ...]:
        review_indexes = tuple(
            index
            for index, offer in enumerate(product.offers)
            if (
                offer.match_level == MatchLevel.REVIEW
                and offer.match_candidate_key == candidate_product_key
            )
        )
        if not review_indexes:
            raise ValueError(
                "Pending review pair was not found: "
                f"{product.key} -> {candidate_product_key}"
            )
        return review_indexes

    @staticmethod
    def _with_match_metadata(
        item: ExternalCatalogItem,
        result: MatchResult,
        candidate_product_key: str,
    ) -> ExternalCatalogItem:
        return replace(
            item,
            match_level=result.level,
            match_score=result.score,
            match_reason=result.reason,
            match_conflicts=result.conflicts,
            match_candidate_key=candidate_product_key,
        )

    @staticmethod
    def _external_key(item: ExternalCatalogItem) -> tuple[str, str]:
        return (
            item.source.strip().casefold(),
            item.external_id.strip(),
        )

    @staticmethod
    def _replace_offer(
        product: MasterCatalogProduct,
        item: ExternalCatalogItem,
    ) -> None:
        for index, existing in enumerate(product.offers):
            if (
                existing.source.strip().casefold()
                == item.source.strip().casefold()
                and existing.external_id.strip() == item.external_id.strip()
            ):
                if item.match_level is None:
                    item = replace(
                        item,
                        match_level=existing.match_level,
                        match_score=existing.match_score,
                        match_reason=existing.match_reason,
                        match_conflicts=existing.match_conflicts,
                        match_candidate_key=existing.match_candidate_key,
                    )
                product.offers[index] = replace(item)
                return
        product.offers.append(item)

    @staticmethod
    def _aware_datetime(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @staticmethod
    def _search_score(query: str, value: str) -> int:
        if query == value:
            return 3
        if value.startswith(query):
            return 2
        if query in value:
            return 1
        return 0
