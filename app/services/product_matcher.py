import re
from difflib import SequenceMatcher

from app.models.catalog import MatchLevel, MatchResult, ProductIdentity


class ProductMatcher:
    """Сопоставляет нормализованные карточки без смешивания вариантов."""

    _variant_fields = ("memory", "color", "revision")

    def match(
        self,
        canonical: ProductIdentity,
        candidate: ProductIdentity,
    ) -> MatchResult:
        """Возвращает уровень уверенности и объяснимую причину решения."""

        variant_conflicts = tuple(
            field_name
            for field_name in self._variant_fields
            if self._values_conflict(
                getattr(canonical, field_name),
                getattr(candidate, field_name),
            )
        )

        if variant_conflicts:
            return MatchResult(
                level=MatchLevel.REJECTED,
                score=0.0,
                reason="variant_conflict",
                conflicts=variant_conflicts,
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

        if self._is_model_family_conflict(canonical.model, candidate.model):
            return MatchResult(
                level=MatchLevel.REJECTED,
                score=0.0,
                reason="different_product",
                conflicts=("model",),
            )

        # A high edit similarity is not evidence that two generations or model
        # codes are the same product (e.g. iPhone 15 Pro / iPhone 16 Pro).
        left_numbers = re.findall(r"\d+", self._normalize(canonical.model) or "")
        right_numbers = re.findall(r"\d+", self._normalize(candidate.model) or "")
        if left_numbers and right_numbers and left_numbers != right_numbers:
            return MatchResult(
                level=MatchLevel.REJECTED,
                score=0.0,
                reason="different_product",
                conflicts=("model",),
            )

        combined_score = round(brand_score * 0.25 + model_score * 0.75, 4)

        if brand_score >= 0.9 and model_score >= 0.9:
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

    @classmethod
    def _tokenize(cls, value: str | None) -> tuple[str, ...]:
        if value is None:
            return ()

        return tuple(
            token
            for token in re.findall(
                r"[a-zа-я0-9]+",
                value.casefold().replace("ё", "е"),
            )
            if token
        )

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
        comparable_values = [
            (
                self._normalize(getattr(left, field_name)),
                self._normalize(getattr(right, field_name)),
            )
            for field_name in self._variant_fields
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

    @classmethod
    def _is_model_family_conflict(
        cls,
        left: str | None,
        right: str | None,
    ) -> bool:
        left_tokens = cls._tokenize(left)
        right_tokens = cls._tokenize(right)

        if not left_tokens or not right_tokens:
            return False

        family_markers = {"air", "lite", "max", "mini", "plus", "pro", "slim", "ultra"}
        left_markers = set(left_tokens) & family_markers
        right_markers = set(right_tokens) & family_markers

        return left_markers != right_markers
