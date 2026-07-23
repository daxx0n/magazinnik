from pathlib import Path


path = Path(__file__).resolve().parents[1] / "app/services/price_service.py"
text = path.read_text()

wrong_canonical = '''                        token.isalpha()
                        and token not in generic_title_words
                        and token not in candidate_code_words
                        and token not in canonical_code_words
'''
correct_canonical = '''                        token.isalpha()
                        and token not in generic_title_words
                        and token not in canonical_code_words
'''
if wrong_canonical not in text:
    raise RuntimeError("Canonical fallback filter marker not found")
text = text.replace(wrong_canonical, correct_canonical, 1)

candidate_section_marker = "        if candidate_brand is None:\n"
section_index = text.find(candidate_section_marker)
if section_index < 0:
    raise RuntimeError("Candidate fallback section not found")
head = text[:section_index]
tail = text[section_index:]
old_candidate = '''                        token.isalpha()
                        and token not in generic_title_words
'''
new_candidate = '''                        token.isalpha()
                        and token not in generic_title_words
                        and token not in candidate_code_words
'''
if old_candidate not in tail:
    raise RuntimeError("Candidate fallback filter marker not found")
tail = tail.replace(old_candidate, new_candidate, 1)
path.write_text(head + tail)
