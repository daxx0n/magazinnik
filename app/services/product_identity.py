import re

from app.models.catalog import ProductIdentity
from app.services.product_variants import (
    base_product_title,
    extract_color_key,
    extract_memory,
)


class ProductIdentityBuilder:
    """Строит нормализованную идентичность товара из исходных данных."""

    _generic_prefixes = {
        "автомагнитола",
        "видеокарта",
        "духовой",
        "кофемашина",
        "монитор",
        "ноутбук",
        "планшет",
        "пылесос",
        "смартфон",
        "телевизор",
        "телефон",
        "холодильник",
        "часы",
        "smartphone",
        "tablet",
        "television",
        "tv",
    }
    _revision_patterns = (
        re.compile(r"\b(?:rev(?:ision)?|рев(?:изия)?)\s*[.:#-]?\s*([a-z0-9.-]+)\b", re.I),
        re.compile(r"\b(cfi-\d{4}[a-z]?)\b", re.I),
        re.compile(r"\b(?:chassis|шасси)\s*([a-z0-9.-]+)\b", re.I),
    )

    def build(
        self,
        title: str,
        *,
        brand: str | None = None,
        model: str | None = None,
        ean: str | None = None,
        mpn: str | None = None,
        revision: str | None = None,
    ) -> ProductIdentity:
        """Возвращает признаки, пригодные для межмагазинного сопоставления."""

        detected_revision = self._normalize_text(revision) or self._extract_revision(title)
        cleaned_title = self._clean_title(title)
        detected_brand = self._normalize_text(brand) or self._extract_brand(cleaned_title)
        detected_model = self._normalize_text(model) or self._extract_model(
            cleaned_title,
            detected_brand,
        )

        return ProductIdentity(
            brand=detected_brand,
            model=detected_model,
            memory=extract_memory(title),
            color=extract_color_key(title),
            revision=detected_revision,
            ean=self._normalize_identifier(ean),
            mpn=self._normalize_identifier(mpn),
        )

    @classmethod
    def _clean_title(cls, title: str) -> str:
        value = base_product_title(title)
        for pattern in cls._revision_patterns:
            value = pattern.sub(" ", value)
        value = value.replace("ё", "е")
        value = re.sub(r"[|,;]+", " ", value)
        return " ".join(value.split()).strip()

    @classmethod
    def _extract_brand(cls, title: str) -> str | None:
        tokens = re.findall(r"[a-zа-я0-9][a-zа-я0-9.+-]*", title, re.I)
        while tokens and tokens[0].casefold() in cls._generic_prefixes:
            tokens.pop(0)
        return cls._normalize_text(tokens[0]) if tokens else None

    @classmethod
    def _extract_model(cls, title: str, brand: str | None) -> str | None:
        tokens = re.findall(r"[a-zа-я0-9][a-zа-я0-9.+-]*", title, re.I)
        while tokens and tokens[0].casefold() in cls._generic_prefixes:
            tokens.pop(0)

        if brand and tokens and cls._normalize_text(tokens[0]) == brand:
            tokens.pop(0)

        return cls._normalize_text(" ".join(tokens))

    @classmethod
    def _extract_revision(cls, title: str) -> str | None:
        for pattern in cls._revision_patterns:
            match = pattern.search(title)
            if match is None:
                continue
            groups = [group for group in match.groups() if group]
            return cls._normalize_text(groups[-1] if groups else match.group(0))
        return None

    @staticmethod
    def _normalize_text(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.casefold().replace("ё", "е")
        normalized = re.sub(r"[^a-zа-я0-9.+-]+", " ", normalized)
        normalized = " ".join(normalized.split())
        return normalized or None

    @staticmethod
    def _normalize_identifier(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = re.sub(r"[^a-z0-9]+", "", value.casefold())
        return normalized or None
