from pathlib import Path

path = Path("app/handlers/search.py")
text = path.read_text(encoding="utf-8")

import_anchor = "from app.services.model_selection import (\n"
if "from app.services.any_color import (" not in text:
    text = text.replace(
        import_anchor,
        "from app.services.any_color import (\n"
        "    aggregate_any_color_results,\n"
        "    load_any_color_results,\n"
        ")\n"
        + import_anchor,
        1,
    )

old = '''    async def load(product: ProductCandidate) -> ComparisonResult | None:
        try:
            return await price_service.search_all_sources_by_onliner_key(
                product.key,
                original_query=None,
            )
        except (ProductNotFoundError, SourceUnavailableError):
            return None

    try:
        results = await asyncio.gather(*(load(product) for product in products))
    except Exception:
        logger.exception("Unexpected any-color comparison error")
        await message.edit_text("Произошла ошибка при сравнении цветов.")
        return

    successful = [result for result in results if result and result.offers]
    if not successful:
        await message.edit_text("Предложения для выбранной памяти не найдены.")
        return

    unique: dict[tuple[str, str], ProductOffer] = {}
    for result in successful:
        for offer in result.offers:
            unique.setdefault(((offer.seller or "").casefold(), offer.url), offer)
    offers = sorted(unique.values(), key=lambda offer: float(offer.price))
    cheapest_result = min(
        successful,
        key=lambda result: min(float(offer.price) for offer in result.offers),
    )
    comparison = replace(
        cheapest_result,
        offers=offers,
        query=original_query or cheapest_result.query,
    )
    product_key = cheapest_result.product_key or products[0].key
'''
new = '''    async def load(product: ProductCandidate) -> ComparisonResult | None:
        try:
            return await price_service.search_all_sources_by_onliner_key(
                product.key,
                original_query=None,
            )
        except (ProductNotFoundError, SourceUnavailableError):
            return None

    results = await load_any_color_results(products, load)
    comparison = aggregate_any_color_results(
        results,
        original_query=original_query,
    )
    if comparison is None:
        await message.edit_text("Предложения для выбранной памяти не найдены.")
        return

    offers = comparison.offers
    product_key = comparison.product_key or products[0].key
'''
if old not in text:
    raise RuntimeError("any-color block not found")
text = text.replace(old, new, 1)

path.write_text(text, encoding="utf-8")
