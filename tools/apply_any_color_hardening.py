import re
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

pattern = re.compile(
    r"    async def load\(product: ProductCandidate\) -> ComparisonResult \| None:\n"
    r".*?"
    r"    product_key = cheapest_result\.product_key or products\[0\]\.key\n",
    re.DOTALL,
)
replacement = '''    async def load(product: ProductCandidate) -> ComparisonResult | None:
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
text, count = pattern.subn(replacement, text, count=1)
if count != 1:
    raise RuntimeError("any-color block not found")

path.write_text(text, encoding="utf-8")
