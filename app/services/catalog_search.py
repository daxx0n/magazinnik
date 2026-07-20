import re
from collections.abc import Iterable
from dataclasses import dataclass

from app.models.catalog import MasterCatalogProduct, ProductIdentity


@dataclass(frozen=True, slots=True)
class _SearchValue:
    value: str
    kind: str


def search_catalog(
    products: Iterable[MasterCatalogProduct],
    query: str,
) -> list[MasterCatalogProduct]:
    """Ищет карточки по названиям, модели, MPN и EAN."""

    normalized_query = _normalize_text(query)
    compact_query = _compact(query)
    if not normalized_query and not compact_query:
        return []

    scored: list[tuple[int, MasterCatalogProduct]] = []
    for product in products:
        score = max(
            (
                _score_value(
                    value=search_value,
                    normalized_query=normalized_query,
                    compact_query=compact_query,
                )
                for search_value in _search_values(product)
            ),
            default=0,
        )
        if score:
            scored.append((score, product))

    scored.sort(
        key=lambda pair: (
            -pair[0],
            pair[1].title.casefold(),
            pair[1].key,
        )
    )
    return [product for _, product in scored]


def _search_values(product: MasterCatalogProduct) -> tuple[_SearchValue, ...]:
    values: list[_SearchValue] = [
        _SearchValue(product.title, "title"),
        *_identity_values(product.identity),
    ]
    for offer in product.offers:
        values.append(_SearchValue(offer.title, "offer_title"))
        if offer.identity is not None:
            values.extend(_identity_values(offer.identity))
    return tuple(value for value in values if value.value.strip())


def _identity_values(identity: ProductIdentity) -> tuple[_SearchValue, ...]:
    values: list[_SearchValue] = []
    brand_model = " ".join(
        part for part in (identity.brand, identity.model) if part
    )
    full_variant = " ".join(
        part
        for part in (
            identity.brand,
            identity.model,
            identity.memory,
            identity.color,
            identity.revision,
        )
        if part
    )
    if brand_model:
        values.append(_SearchValue(brand_model, "brand_model"))
    if full_variant and full_variant != brand_model:
        values.append(_SearchValue(full_variant, "variant"))
    if identity.model:
        values.append(_SearchValue(identity.model, "model"))
    if identity.mpn:
        values.append(_SearchValue(identity.mpn, "identifier"))
    if identity.ean:
        values.append(_SearchValue(identity.ean, "identifier"))
    return tuple(values)


def _score_value(
    value: _SearchValue,
    normalized_query: str,
    compact_query: str,
) -> int:
    normalized_value = _normalize_text(value.value)
    compact_value = _compact(value.value)

    if value.kind == "identifier":
        if compact_query and compact_query == compact_value:
            return 1_000
        if (
            len(compact_query) >= 6
            and compact_query
            and compact_value.startswith(compact_query)
        ):
            return 850
        return 0

    if compact_query and compact_query == compact_value:
        return {
            "model": 950,
            "brand_model": 925,
            "variant": 900,
            "title": 875,
            "offer_title": 850,
        }.get(value.kind, 800)

    if normalized_query == normalized_value:
        return 825

    query_tokens = set(normalized_query.split())
    value_tokens = set(normalized_value.split())
    if query_tokens and query_tokens.issubset(value_tokens):
        return {
            "brand_model": 760,
            "model": 750,
            "variant": 725,
            "title": 700,
            "offer_title": 675,
        }.get(value.kind, 650)

    if normalized_value.startswith(normalized_query):
        return 600
    if normalized_query in normalized_value:
        return 500
    if len(compact_query) >= 4 and compact_query in compact_value:
        return 450
    return 0


def _normalize_text(value: str) -> str:
    normalized = value.casefold().replace("ё", "е")
    normalized = re.sub(r"[^a-zа-я0-9]+", " ", normalized)
    return " ".join(normalized.split())


def _compact(value: str) -> str:
    return re.sub(
        r"[^a-zа-я0-9]+",
        "",
        value.casefold().replace("ё", "е"),
    )
