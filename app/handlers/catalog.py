import logging
import os

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.handlers import search
from app.models.catalog import CatalogSnapshotMetrics, MatchReview
from app.models.catalog_metrics import CatalogMetrics
from app.services.catalog_service import CatalogService


router = Router(name="catalog")
logger = logging.getLogger(__name__)


@router.message(Command("catalog_stats"))
async def handle_catalog_stats(message: Message) -> None:
    """Показывает метрики дедупликации и свежести каталога."""

    if not _is_allowed(message):
        await message.answer("Команда доступна только администратору.")
        return

    try:
        service = get_catalog_service()
        text = format_catalog_stats(
            snapshot=service.snapshot_metrics(),
            runtime=service.metrics,
            storage_backend=service.storage_backend,
            storage_path=service.storage_path,
        )
    except Exception:
        logger.exception("Catalog metrics command failed")
        await message.answer("Не удалось получить метрики каталога.")
        return

    await message.answer(text)


@router.message(Command("catalog_reviews"))
async def handle_catalog_reviews(message: Message) -> None:
    """Показывает последние спорные совпадения для проверки."""

    if not _is_allowed(message):
        await message.answer("Команда доступна только администратору.")
        return

    try:
        service = get_catalog_service()
        snapshot = service.snapshot_metrics()
        reviews = service.pending_reviews(limit=10)
        text = format_catalog_reviews(
            reviews,
            total=snapshot.review_matches,
        )
    except Exception:
        logger.exception("Catalog reviews command failed")
        await message.answer("Не удалось получить очередь проверки.")
        return

    await message.answer(text, disable_web_page_preview=True)


@router.message(Command("catalog_review_accept"))
async def handle_catalog_review_accept(message: Message) -> None:
    """Подтверждает объединение спорной карточки с кандидатом."""

    await _handle_review_decision(message, accept=True)


@router.message(Command("catalog_review_reject"))
async def handle_catalog_review_reject(message: Message) -> None:
    """Подтверждает, что спорные карточки являются разными."""

    await _handle_review_decision(message, accept=False)


async def _handle_review_decision(
    message: Message,
    accept: bool,
) -> None:
    if not _is_allowed(message):
        await message.answer("Команда доступна только администратору.")
        return

    command_name = (
        "catalog_review_accept"
        if accept
        else "catalog_review_reject"
    )
    parts = (message.text or "").split()
    if len(parts) != 3:
        await message.answer(
            "Использование:\n"
            f"/{command_name} PRODUCT_KEY CANDIDATE_KEY"
        )
        return

    product_key, candidate_product_key = parts[1:]
    try:
        service = get_catalog_service()
        if accept:
            product = service.accept_review(
                product_key,
                candidate_product_key,
            )
            result_text = (
                "✅ Карточки объединены.\n"
                f"Мастер-карточка: {product.key} — {product.title}\n"
                f"Офферов: {len(product.offers)}"
            )
        else:
            product = service.reject_review(
                product_key,
                candidate_product_key,
            )
            result_text = (
                "🚫 Карточки оставлены раздельными.\n"
                f"Карточка: {product.key} — {product.title}"
            )
    except ValueError as error:
        await message.answer(f"Не удалось применить решение: {error}")
        return
    except Exception:
        logger.exception(
            "Catalog review decision failed: accept=%s product=%s candidate=%s",
            accept,
            product_key,
            candidate_product_key,
        )
        await message.answer("Не удалось сохранить решение проверки.")
        return

    await message.answer(result_text)


def get_catalog_service() -> CatalogService:
    """Использует тот же экземпляр каталога, что и рабочий поиск."""

    return search.price_service._catalog_service


def format_catalog_stats(
    snapshot: CatalogSnapshotMetrics,
    runtime: CatalogMetrics,
    storage_backend: str | None = None,
    storage_path: str | None = None,
) -> str:
    """Формирует компактный отчёт качества мастер-каталога."""

    lines = [
        "📊 Мастер-каталог",
        "",
    ]

    if storage_backend:
        lines.append(f"Хранилище: {storage_backend}")
    if storage_path:
        lines.append(f"Путь: {storage_path}")
    if storage_backend or storage_path:
        lines.append("")

    lines.extend(
        [
            f"Карточек: {snapshot.product_count}",
            f"Офферов: {snapshot.offer_count}",
            (
                "Объединённых офферов: "
                f"{snapshot.merged_offer_count} "
                f"({snapshot.duplicate_rate:.1%})"
            ),
            f"Карточек с одним источником: {snapshot.single_source_products}",
            f"Карточек с несколькими источниками: {snapshot.multi_source_products}",
            "",
            "Качество сопоставления:",
            f"• exact: {snapshot.exact_matches}",
            f"• probable: {snapshot.probable_matches}",
            f"• review: {snapshot.review_matches}",
            f"• rejected: {snapshot.rejected_matches}",
            (
                "• доля exact среди автоматических: "
                f"{snapshot.exact_share:.1%}"
            ),
            "",
            "Свежесть за 24 часа:",
            f"• свежих офферов: {snapshot.fresh_offers}",
            f"• устаревших офферов: {snapshot.stale_offers}",
            f"• недоступных офферов: {snapshot.unavailable_offers}",
            "",
            "Рабочие пакеты после запуска:",
            f"• обработано: {runtime.batches}",
            f"• однозначных: {runtime.single_product_batches}",
            f"• неоднозначных: {runtime.ambiguous_batches}",
            (
                "• пригодность мастер-представления: "
                f"{runtime.presentation_eligibility_rate:.1%}"
            ),
        ]
    )

    if snapshot.source_offer_counts:
        lines.extend(["", "Источники:"])
        lines.extend(
            f"• {source}: {count}"
            for source, count in snapshot.source_offer_counts
        )

    return "\n".join(lines)


def format_catalog_reviews(
    reviews: tuple[MatchReview, ...],
    total: int,
) -> str:
    """Формирует очередь спорных совпадений для ручной проверки."""

    if not reviews:
        return "🧩 Очередь проверки пуста."

    reason_labels = {
        "ambiguous_brand_or_model": "неоднозначный бренд или модель",
        "different_product": "возможно другой товар",
        "variant_conflict": "конфликт модификации",
    }
    lines = [
        "🧩 Очередь проверки",
        f"Всего спорных совпадений: {total}",
        f"Показано последних: {len(reviews)}",
        "",
    ]

    for index, review in enumerate(reviews, start=1):
        lines.extend(
            [
                f"{index}. {review.incoming_title}",
                f"   Источник: {review.source}",
                (
                    f"   Новая карточка: {review.product_key} — "
                    f"{review.product_title}"
                ),
                (
                    f"   Кандидат: {review.candidate_product_key} — "
                    f"{review.candidate_product_title}"
                ),
                (
                    "   Решение: "
                    f"{reason_labels.get(review.reason, review.reason)}, "
                    f"score={review.score:.3f}"
                ),
                (
                    "   ✅ /catalog_review_accept "
                    f"{review.product_key} {review.candidate_product_key}"
                ),
                (
                    "   🚫 /catalog_review_reject "
                    f"{review.product_key} {review.candidate_product_key}"
                ),
                "",
            ]
        )

    return "\n".join(lines).rstrip()


def _is_allowed(message: Message) -> bool:
    raw_ids = os.getenv("CATALOG_ADMIN_CHAT_IDS", "").strip()
    if not raw_ids:
        return True

    allowed_ids: set[int] = set()
    for raw_id in raw_ids.split(","):
        try:
            allowed_ids.add(int(raw_id.strip()))
        except ValueError:
            logger.warning("Invalid CATALOG_ADMIN_CHAT_IDS value: %r", raw_id)

    chat = getattr(message, "chat", None)
    chat_id = getattr(chat, "id", None)
    return isinstance(chat_id, int) and chat_id in allowed_ids
