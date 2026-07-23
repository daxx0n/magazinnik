import unittest

from app.services.variant_matching import (
    bundle_identity,
    device_configuration,
    explicit_region,
    memory_signature,
    neutralize_variant_markers,
    product_condition,
    sim_configuration,
    variant_mismatch_reason,
)


class VariantMatchingTest(unittest.TestCase):
    def test_normalizes_memory_units_and_ram_storage_pairs(self) -> None:
        self.assertEqual(memory_signature("Phone 1TB"), memory_signature("Phone 1024GB"))
        self.assertEqual(
            memory_signature("Phone 12/256GB"),
            memory_signature("Phone 12GB/256 ГБ"),
        )
        self.assertIsNone(
            variant_mismatch_reason("Phone 256GB", "Phone 12GB/256GB")
        )
        self.assertEqual(
            variant_mismatch_reason("Phone 12GB/256GB", "Phone 256GB"),
            "memory",
        )

    def test_regions_are_strict_only_when_both_are_explicit(self) -> None:
        self.assertEqual(explicit_region("Phone (EU)"), "eu")
        self.assertEqual(explicit_region("Phone Global"), "global")
        self.assertEqual(
            variant_mismatch_reason("Phone EU", "Phone US"),
            "region",
        )
        self.assertIsNone(variant_mismatch_reason("Phone EU", "Phone"))
        self.assertIsNone(variant_mismatch_reason("Phone", "Phone China"))

    def test_sim_variants_are_distinct_without_penalizing_missing_data(self) -> None:
        cases = {
            "Phone Dual eSIM": "dual_esim",
            "Phone nano-SIM + eSIM": "hybrid",
            "Phone eSIM only": "esim_only",
            "Phone Dual SIM": "dual_sim",
            "Phone Single SIM": "single_sim",
        }
        for title, expected in cases.items():
            with self.subTest(title=title):
                self.assertEqual(sim_configuration(title), expected)

        self.assertEqual(
            variant_mismatch_reason("Phone Dual SIM", "Phone eSIM only"),
            "sim",
        )
        self.assertIsNone(variant_mismatch_reason("Phone", "Phone Dual SIM"))

    def test_network_and_hardware_configurations_remain_distinct(self) -> None:
        self.assertEqual(device_configuration("Tablet LTE"), "4g")
        self.assertEqual(device_configuration("Tablet 5G"), "5g")
        self.assertEqual(
            variant_mismatch_reason("Tablet Wi-Fi", "Tablet 5G"),
            "configuration",
        )
        self.assertEqual(
            variant_mismatch_reason("Console Digital Edition", "Console с дисководом"),
            "configuration",
        )
        self.assertIsNone(variant_mismatch_reason("Tablet", "Tablet 5G"))

    def test_sim_and_cellular_plus_signs_are_not_bundles(self) -> None:
        self.assertIsNone(bundle_identity("Phone nano-SIM + eSIM"))
        self.assertIsNone(bundle_identity("Watch GPS + Cellular"))

    def test_condition_and_bundle_content_are_material_variants(self) -> None:
        self.assertEqual(product_condition("Phone Open Box"), "open_box")
        self.assertEqual(product_condition("Phone витринный образец"), "open_box")
        self.assertEqual(
            variant_mismatch_reason("Phone", "Phone Open Box"),
            "condition",
        )
        self.assertEqual(bundle_identity("PS5 + DualSense").marker, "controller")
        self.assertEqual(
            variant_mismatch_reason("PS5 + DualSense", "PS5 + Headset"),
            "bundle",
        )
        self.assertEqual(
            variant_mismatch_reason("PS5", "PS5 + DualSense"),
            "bundle",
        )

    def test_neutralization_preserves_model_and_version_words(self) -> None:
        self.assertEqual(
            neutralize_variant_markers(
                "Apple iPhone 17 Pro 12GB/256GB EU Dual SIM"
            ),
            "Apple iPhone 17 Pro",
        )
        self.assertEqual(
            neutralize_variant_markers("Roborock Q8 Max+ 256GB Global"),
            "Roborock Q8 Max+",
        )


if __name__ == "__main__":
    unittest.main()
