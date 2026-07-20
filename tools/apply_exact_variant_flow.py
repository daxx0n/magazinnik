from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SELECTION_IMPORT = """from app.services.model_selection import (
    group_model_variants,
    requested_color_key,
    selected_color_label,
)
"""


def patch_price_service() -> None:
    path = ROOT / "app/services/price_service.py"
    text = path.read_text(encoding="utf-8")
    old = """        requested_query = self._onliner_queries.get(
            product_key,
            canonical_title,
        )
"""
    new = """        # После выбора карточки именно полное название варианта,
        # а не исходный широкий запрос, является эталоном мэтчинга.
        requested_query = canonical_title
"""
    if old in text:
        text = text.replace(old, new, 1)
    elif new not in text:
        raise RuntimeError("Missing selected candidate reference")
    path.write_text(text, encoding="utf-8")


def patch_search_handler() -> None:
    path = ROOT / "app/handlers/search.py"
    text = path.read_text(encoding="utf-8")

    text = text.replace(SELECTION_IMPORT, "")
    marker = "from app.services.price_service import PriceService\n"
    if marker not in text:
        raise RuntimeError("Missing PriceService import")
    text = text.replace(marker, SELECTION_IMPORT + marker, 1)
    text = text.replace("    group_product_variants,\n", "")
    text = text.replace("group_product_variants(", "group_model_variants(")

    while text.count("    extract_memory,\n") > 1:
        text = text.replace("    extract_memory,\n", "", 1)
    if "    extract_memory,\n" not in text:
        text = text.replace(
            "    display_product_title,\n",
            "    display_product_title,\n    extract_memory,\n",
            1,
        )

    old_variant_flow = """    memory_groups = group_by_memory(group.products)

    if len(memory_groups) == 1:
        await show_color_selection(
            message=callback.message,
            group=group,
            products=memory_groups[0][1],
            back_callback=(
                f"olp:{search_id}:"
                f"{group_index // PRODUCT_PAGE_SIZE}"
            ),
        )
        return

    await callback.message.edit_text(
        f"📱 {group.title}\n\n"
        "Выбери объём памяти:",
        reply_markup=build_memory_keyboard(
            search_id=search_id,
            group_index=group_index,
            memory_groups=memory_groups,
        ),
    )
"""
    new_variant_flow = """    await show_color_selection(
        message=callback.message,
        group=group,
        products=group.products,
        back_callback=(
            f"olp:{search_id}:"
            f"{group_index // PRODUCT_PAGE_SIZE}"
        ),
    )
"""
    if old_variant_flow in text:
        text = text.replace(old_variant_flow, new_variant_flow, 1)
    elif new_variant_flow not in text:
        raise RuntimeError("Missing model-to-color flow")

    old_single = """        if len(group.products) == 1:
            callback_data = (
                f"ol:{group.products[0].key}"
            )
"""
    new_single = """        if (
            len(group.products) == 1
            and requested_color_key(group.products[0].title) is None
        ):
            callback_data = (
                f"ol:{group.products[0].key}"
            )
"""
    if old_single in text:
        text = text.replace(old_single, new_single, 1)
    elif new_single not in text:
        raise RuntimeError("Missing single-product routing")

    new_show_color = '''async def show_color_selection(
    message: Message,
    group: ProductVariantGroup,
    products: list[ProductCandidate],
    back_callback: str,
) -> None:
    """Показывает цвет; память уточняется в подписи варианта."""

    colored_products = [
        product
        for product in products
        if requested_color_key(product.title) is not None
    ]
    selectable_products = colored_products or products

    choices: dict[tuple[str, str], ProductCandidate] = {}
    for product in selectable_products:
        color_key = requested_color_key(product.title) or "unknown"
        memory = extract_memory(product.title) or "Без выбора памяти"
        choices.setdefault((color_key, memory), product)

    if len(choices) == 1:
        only_product = next(iter(choices.values()))
        if requested_color_key(only_product.title) is None:
            await load_product_comparison(
                message=message,
                product_key=only_product.key,
            )
            return

    color_counts = Counter(
        color_key for color_key, _ in choices
    )
    builder = InlineKeyboardBuilder()
    sorted_choices = sorted(
        choices.items(),
        key=lambda item: (
            (selected_color_label(item[1].title) or "").casefold(),
            item[0][1],
            item[1].title.casefold(),
        ),
    )

    for (color_key, memory), product in sorted_choices:
        label = selected_color_label(product.title) or "Цвет не указан"
        if color_counts[color_key] > 1:
            label = f"{label} · {memory}"

        builder.row(
            InlineKeyboardButton(
                text=(
                    label
                    if len(label) <= 58
                    else label[:55] + "..."
                ),
                callback_data=f"ol:{product.key}",
            )
        )

    builder.row(
        InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=back_callback,
        )
    )

    await message.edit_text(
        f"📱 {group.title}\n\n"
        "Выбери цвет. Если у цвета несколько вариантов памяти, "
        "она указана в кнопке:",
        reply_markup=builder.as_markup(),
    )


'''
    pattern = re.compile(
        r"async def show_color_selection\(.*?\n\n\ndef store_product_search\(",
        re.DOTALL,
    )
    match = pattern.search(text)
    if match is None:
        raise RuntimeError("Missing show_color_selection block")
    text = (
        text[:match.start()]
        + new_show_color
        + "def store_product_search("
        + text[match.end():]
    )

    path.write_text(text, encoding="utf-8")


def main() -> None:
    patch_price_service()
    patch_search_handler()


if __name__ == "__main__":
    main()
