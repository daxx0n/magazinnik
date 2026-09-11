"""Query-aware relevance rules for the source-independent catalog."""

from __future__ import annotations

import re

from app.models.product import ProductCandidate
from app.services.variant_matching import product_condition


_IPHONE_TOKEN = re.compile(r"\biphone\b", re.IGNORECASE)
_IPHONE_MODEL = re.compile(
    r"\biphone\s*(?:"
    r"se(?:\s*(?:\(?\d{4}\)?|[123](?:st|nd|rd)?\s*gen(?:eration)?))?"
    r"|x(?:r|s(?:\s*max)?)?"
    r"|\d{1,2}(?:e|s|c)?(?:\s*(?:pro(?:\s*max)?|plus|mini|air|max))?"
    r")\b",
    re.IGNORECASE,
)

# These describe a compatible product, spare part or service rather than a
# phone. Keep the list bilingual because retailer titles mix RU/EN freely.
_PHONE_ACCESSORY = re.compile(
    r"\b(?:"
    r"cases?|covers?|bumper|wallet|pouch|чех\w*|бампер\w*|сумк\w*|"
    r"cables?|cords?|кабел\w*|шнур\w*|"
    r"chargers?|charging|power\s*adapter|адаптер\w*|заряд\w*|переходник\w*|"
    r"screen\s*protector|protective\s*glass|tempered\s*glass|glass|"
    r"стекл\w*|пленк\w*|защит\w*\s+(?:стекл\w*|пленк\w*)|"
    r"holders?|mounts?|stands?|docks?|держател\w*|креплен\w*|подставк\w*|"
    r"batter(?:y|ies)|power\s*bank|аккумулятор\w*|пауэрбанк\w*|"
    r"headphones?|headsets?|earbuds?|airpods|наушник\w*|гарнитур\w*|"
    r"display|touchscreen|digitizer|housing|back\s*cover|spare\s*parts?|"
    r"диспле\w*|тачскрин\w*|экран\w*|корпус\w*|крышк\w*|запчаст\w*|"
    r"camera\s*(?:glass|protector|lens)|линз\w*|накладк\w*|"
    r"skins?|stickers?|наклейк\w*|муляж\w*|макет\w*|dummy|replica|копи\w*|"
    r"ремонт\w*|замен\w*"
    r")\b",
    re.IGNORECASE,
)
_ACCESSORY_URL = re.compile(
    r"(?:phonecase|protectiveglass|charger|cable|headphones|accessor|sparepart)",
    re.IGNORECASE,
)
_NON_NEW = re.compile(
    r"(?:\bб\s*/?\s*у\b|\bбу\b|\bsecond[-\s]?hand\b|"
    r"\btrade[-\s]?in\b|\bдемо\b|\bвитринн\w*\b|\bуцен\w*\b)",
    re.IGNORECASE,
)


def is_iphone_phone_query(query: str | None) -> bool:
    """Return true when iPhone means the phone, not an requested accessory."""

    if not query or _IPHONE_TOKEN.search(query) is None:
        return False
    return _PHONE_ACCESSORY.search(query) is None


def is_catalog_record_relevant(
    query: str,
    title: str,
    url: str = "",
) -> bool:
    """Reject category pollution for intents that have strict semantics."""

    if not is_iphone_phone_query(query):
        return True
    if product_condition(title) != "new" or _NON_NEW.search(title):
        return False
    if _PHONE_ACCESSORY.search(title) or _ACCESSORY_URL.search(url):
        return False
    return _IPHONE_MODEL.search(title) is not None


def filter_catalog_candidates(
    candidates: list[ProductCandidate],
    query: str,
) -> list[ProductCandidate]:
    """Apply the same policy to fresh and already persisted candidates."""

    return [
        candidate
        for candidate in candidates
        if is_catalog_record_relevant(query, candidate.title, candidate.url)
    ]
