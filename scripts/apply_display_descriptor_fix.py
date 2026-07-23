from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file_path = Path(path)
    content = file_path.read_text(encoding="utf-8")
    if content.count(old) != 1:
        raise RuntimeError(
            f"Expected one match in {path}, found {content.count(old)}"
        )
    file_path.write_text(content.replace(old, new, 1), encoding="utf-8")


replace_once(
    "app/services/price_service.py",
    '''            normalized = normalized.replace("ё", "е")
            normalized = re.sub(
                r"\\bps\\s*([45])\\b",
''',
    '''            normalized = normalized.replace("ё", "е")
            normalized = re.sub(
                r"\\bmini[\\s-]*led\\b",
                "miniled",
                normalized,
            )
            normalized = re.sub(
                r"\\bps\\s*([45])\\b",
''',
)

replace_once(
    "app/services/price_service.py",
    '''            "headphones",
            "laptop",
            "monitor",
''',
    '''            "ai",
            "headphones",
            "laptop",
            "lcd",
            "led",
            "microled",
            "miniled",
            "monitor",
            "nanocell",
            "neoqled",
            "oled",
            "qled",
            "qned",
            "smart",
            "uhd",
''',
)

path = Path("tests/test_full_model_code_matching.py")
content = path.read_text(encoding="utf-8")
marker = '''    def test_catalog_matcher_rejects_wrong_diagonal(self) -> None:
'''
insert = '''    def test_display_technology_prefix_does_not_replace_brand(self) -> None:
        self.assertIsNone(
            CatalogFirstPriceService._model_mismatch_reason(
                canonical_title=CANONICAL,
                candidate_title="MiniLED телевизор LG QNED AI QNED70 50QNED70B6C",
                requested_title=CANONICAL,
            )
        )
        self.assertEqual(
            CatalogFirstPriceService._model_mismatch_reason(
                canonical_title=CANONICAL,
                candidate_title="OLED телевизор Samsung 50QNED70B6C",
                requested_title=CANONICAL,
            ),
            "brand",
        )

'''
if content.count(marker) != 1:
    raise RuntimeError("Test insertion marker was not found exactly once")
path.write_text(content.replace(marker, insert + marker, 1), encoding="utf-8")

Path("scripts/apply_display_descriptor_fix.py").unlink()
Path(".github/workflows/apply-display-descriptor-fix.yml").unlink()
