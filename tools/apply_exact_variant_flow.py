from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count == 0:
        if new in text:
            return text
        raise RuntimeError(f"Missing replacement target: {label}")
    if count != 1:
        raise RuntimeError(f"Expected one target for {label}, found {count}")
    return text.replace(old, new, 1)


def patch_price_service() -> None:
    path = ROOT / "app/services/price_service.py"
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        """        requested_query = self._onliner_queries.get(\n            product_key,\n            canonical_title,\n        )\n""",
        """        # После выбора карточки именно полное название варианта,\n        # а не исходный широкий запрос, является эталоном мэтчинга.\n        requested_query = canonical_title\n""",
        "selected candidate reference",
    )
    path.write_text(text, encoding="utf-8")


def patch_search_handler() -> None:
    path = ROOT / "app/handlers/search.py"
    text = path.read_text(encoding="utf-8")

    text = replace_once(
        text,
        "from app.services.price_service import PriceService\n",
        """from app.services.model_selection import (\n    group_model_variants,\n    requested_color_key,\n    selected_color_label,\n)\nfrom app.services.price_service import PriceService\n""",
        "selection imports",
    )
    text = text.replace("    group_product_variants,\n", "")
    text = replace_once(
        text,
        "    display_product_title,\n",
        "    display_product_title,\n    extract_memory,\n",
        "memory import",
    )
    text = text.replace("group_product_variants(", "group_model_variants(")

    old_variant_flow = """    memory_groups = group_by_memory(group.products)\n\n    if len(memory_groups) == 1:\n        await show_color_selection(\n            message=callback.message,\n            group=group,\n            products=memory_groups[0][1],\n            back_callback=(\n                f\"olp:{search_id}:\"\n                f\"{group_index // PRODUCT_PAGE_SIZE}\"\n            ),\n        )\n        return\n\n    await callback.message.edit_text(\n        f\"📱 {group.title}\\n\\n\"\n        \"Выбери объём памяти:\",\n        reply_markup=build_memory_keyboard(\n            search_id=search_id,\n            group_index=group_index,\n            memory_groups=memory_groups,\n        ),\n    )\n"""
    new_variant_flow = """    await show_color_selection(\n        message=callback.message,\n        group=group,\n        products=group.products,\n        back_callback=(\n            f\"olp:{search_id}:\"\n            f\"{group_index // PRODUCT_PAGE_SIZE}\"\n        ),\n    )\n"""
    text = replace_once(
        text,
        old_variant_flow,
        new_variant_flow,
        "model to color flow",
    )

    text = replace_once(
        text,
        """        if len(group.products) == 1:\n            callback_data = (\n                f\"ol:{group.products[0].key}\"\n            )\n""",
        """        if (\n            len(group.products) == 1\n            and requested_color_key(group.products[0].title) is None\n        ):\n            callback_data = (\n                f\"ol:{group.products[0].key}\"\n            )\n""",
        "single colored product routing",
    )

    new_show_color = '''async def show_color_selection(\n    message: Message,\n    group: ProductVariantGroup,\n    products: list[ProductCandidate],\n    back_callback: str,\n) -> None:\n    """Показывает цвет; память уточняется в подписи варианта."""\n\n    choices: dict[tuple[str, str], ProductCandidate] = {}\n    for product in products:\n        color_key = requested_color_key(product.title) or "unknown"\n        memory = extract_memory(product.title) or "Без выбора памяти"\n        choices.setdefault((color_key, memory), product)\n\n    if len(choices) == 1:\n        only_product = next(iter(choices.values()))\n        if requested_color_key(only_product.title) is None:\n            await load_product_comparison(\n                message=message,\n                product_key=only_product.key,\n            )\n            return\n\n    color_counts = Counter(\n        color_key for color_key, _ in choices\n    )\n    builder = InlineKeyboardBuilder()\n    sorted_choices = sorted(\n        choices.items(),\n        key=lambda item: (\n            (selected_color_label(item[1].title) or "").casefold(),\n            item[0][1],\n            item[1].title.casefold(),\n        ),\n    )\n\n    for (color_key, memory), product in sorted_choices:\n        label = selected_color_label(product.title) or "Цвет не указан"\n        if color_counts[color_key] > 1:\n            label = f"{label} · {memory}"\n\n        builder.row(\n            InlineKeyboardButton(\n                text=(\n                    label\n                    if len(label) <= 58\n                    else label[:55] + "..."\n                ),\n                callback_data=f"ol:{product.key}",\n            )\n        )\n\n    builder.row(\n        InlineKeyboardButton(\n            text="⬅️ Назад",\n            callback_data=back_callback,\n        )\n    )\n\n    await message.edit_text(\n        f"📱 {group.title}\\n\\n"\n        "Выбери цвет. Если у цвета несколько вариантов памяти, "\n        "она указана в кнопке:",\n        reply_markup=builder.as_markup(),\n    )\n\n\n'''
    pattern = re.compile(
        r"async def show_color_selection\(.*?\n\n\ndef store_product_search\(",
        re.DOTALL,
    )
    match = pattern.search(text)
    if match is None:
        if new_show_color in text:
            pass
        else:
            raise RuntimeError("Missing show_color_selection block")
    else:
        text = text[:match.start()] + new_show_color + "def store_product_search(" + text[match.end():]

    path.write_text(text, encoding="utf-8")


def main() -> None:
    patch_price_service()
    patch_search_handler()


if __name__ == "__main__":
    main()
