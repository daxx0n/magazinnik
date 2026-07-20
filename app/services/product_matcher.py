import re
from difflib import SequenceMatcher

from app.models.catalog import MatchLevel, MatchResult, ProductIdentity


class ProductMatcher:
    """Сопоставляет нормализованные карточки без смешивания вариантов."""

    _conflict_fields = ("brand", "model", "memory", "color", "revision")

    def match(
        self,
        canonical: ProductIdentity,
        candidate: ProductIdentity,
    ) -> MatchResult:
        """Возвращает уровень уверенности и объяснимую причину решения."""

        conflicts = tuple(
            field_name
            for field_name in self._conflict_fields
            if self._values_conflict(
                getattr(canonical, field_name),
                getattr(candidate, field_name),
            )
        )

        if conflicts:
            return MatchResult(
                level=MatchLevel.REJECTED,
                score=0.0,
                reason="variant_conflict",
                conflicts=conflicts,
            )

        if self._same_identifier(canonical.ean, candidate.ean):
            return MatchResult(
                level=MatchLevel.EXACT,
                score=1.0,
                reason="same_ean",
            )

        if self._same_identifier(canonical.mpn, candidate.mpn):
            return MatchResult(
                level=MatchLevel.EXACT,
                score=0.99,
                reason="same_mpn",
            )

        brand_score = self._similarity(canonical.brand, candidate.brand)
        model_score = self._similarity(canonical.model, candidate.model)

        if brand_score == 1.0 and model_score == 1.0:
            if self._same_variant(canonical, candidate):
                return MatchResult(
                    level=MatchLevel.EXACT,
                    score=0.96,
                    reason="same_model_and_variant",
                )

            return MatchResult(
                level=MatchLevel.PROBABLE,
                score=0.9,
                reason="same_model_no_variant_conflicts",
            )

        combined_score = round(brand_score * 0.25 + model_score * 0.75, 4)

        if combined_score >= 0.9:
            return MatchResult(
                level=MatchLevel.PROBABLE,
                score=combined_score,
                reason="similar_brand_and_model",
            )

        if combined_score >= 0.72:
            return MatchResult(
                level=MatchLevel.REVIEW,
                score=combined_score,
                reason="ambiguous_brand_or_model",
            )

        return MatchResult(
            level=MatchLevel.REJECTED,
            score=combined_score,
            reason="different_product",
        )

    @staticmethod
    def _normalize(value: str | None) -> str | None:
        if value is None:
            return None

        normalized = value.casefold().replace("ё", "е")
        normalized = re.sub(r"[^a-zа-я0-9]+", "", normalized)
        return normalized or None

    def _values_conflict(
        self,
        left: str | None,
        right: str | None,
    ) -> bool:
        normalized_left = self._normalize(left)
        normalized_right = self._normalize(right)
        return (
            normalized_left is not None
            and normalized_right is not None
            and normalized_left != normalized_right
        )

    def _same_identifier(
        self,
        left: str | None,
        right: str | None,
    ) -> bool:
        normalized_left = self._normalize(left)
        normalized_right = self._normalize(right)
        return (
            normalized_left is not None
            and normalized_left == normalized_right
        )

    def _similarity(
        self,
        left: str | None,
        right: str | None,
    ) -> float:
        normalized_left = self._normalize(left)
        normalized_right = self._normalize(right)

        if normalized_left is None or normalized_right is None:
            return 0.0

        return SequenceMatcher(
            None,
            normalized_left,
            normalized_right,
        ).ratio()

    def _same_variant(
        self,
        left: ProductIdentity,
        right: ProductIdentity,
    ) -> bool:
        variant_fields = ("memory", "color", "revision")
        comparable_values = [
            (
                self._normalize(getattr(left, field_name)),
                self._normalize(getattr(right, field_name)),
            )
            for field_name in variant_fields
        ]
        known_values = [
            values
            for values in comparable_values
            if values[0] is not None and values[1] is not None
        ]
        return bool(known_values) and all(
            left_value == right_value
            for left_value, right_value in known_values
        )
