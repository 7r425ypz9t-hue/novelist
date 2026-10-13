"""Arabic text primitives (FR04 word count, normalization, patching, diff, sanitization)."""

import pytest

from nis.text import (
    PatchMismatch,
    apply_ops,
    count_words,
    diff_texts,
    doc_from_plain,
    doc_to_plain,
    normalize_ar,
    sanitize_doc,
    search_tokens,
)


@pytest.mark.parametrize(
    ("text", "n"),
    [
        ("ذهبَ الولدُ إلى المدرسةِ", 4),           # tashkeel does not split words
        ("وقالــت: «نعم»، ثم مضت.", 4),           # tatweel ignored, punctuation not counted
        ("في عام 1958 افتُتح الميناء", 5),        # numbers count as one word
        ("He said مرحباً yesterday", 4),           # mixed scripts
        ("،،، ... !!", 0),
        ("٢٠٢٦ سنة", 2),                           # eastern digits
    ],
)
def test_arabic_word_count(text, n):
    assert count_words(text) == n


def test_normalization_unifies_letter_variants():
    assert normalize_ar("أحمد إلى آمال مدرسة مستشفى") == "احمد الي امال مدرسه مستشفي"
    assert search_tokens("والمدرسة") == search_tokens("المدرسه")


def test_apply_replace_and_delete_ops():
    doc = doc_from_plain("الفقرة الأولى, هنا\n\nالفقرة الثانية\n\nالفقرة الثانية")
    new = apply_ops(doc, [
        {"op": "replace_text", "block": 0, "start": 13, "end": 14, "expected": ",", "text": "،"},
        {"op": "delete_block", "block": 2, "expected": "الفقرة الثانية"},
    ])
    assert doc_to_plain(new) == "الفقرة الأولى، هنا\n\nالفقرة الثانية"
    assert doc_to_plain(doc).count("الثانية") == 2  # original untouched


def test_apply_rejects_changed_base_text():
    doc = doc_from_plain("نص تغيّر")
    with pytest.raises(PatchMismatch):
        apply_ops(doc, [{"op": "replace_text", "block": 0, "start": 0, "end": 2, "expected": "كلا", "text": "x"}])


def test_marks_survive_partial_replace():
    doc = {"type": "doc", "content": [{"type": "paragraph", "content": [
        {"type": "text", "text": "قال "}, {"type": "text", "text": "نادر", "marks": [{"type": "bold"}]},
        {"type": "text", "text": " ذلك"}]}]}
    new = apply_ops(doc, [{"op": "replace_text", "block": 0, "start": 4, "end": 8, "expected": "نادر", "text": "مازن"}])
    inline = new["content"][0]["content"]
    assert doc_to_plain(new) == "قال مازن ذلك"
    assert any(n.get("marks") == [{"type": "bold"}] and n["text"] == "مازن" for n in inline)


def test_diff_is_word_level_and_paragraph_aligned():
    segs = diff_texts("البحر هادئ اليوم\n\nفقرة ثابتة", "البحر هائج اليوم\n\nفقرة ثابتة")
    assert {"op": "delete", "text": "هادئ"} in segs and {"op": "insert", "text": "هائج"} in segs


def test_sanitize_strips_unknown_nodes_marks_and_attrs():
    dirty = {"type": "doc", "content": [
        {"type": "script", "content": [{"type": "text", "text": "alert(1)"}]},
        {"type": "paragraph", "attrs": {"onclick": "x", "dir": "rtl"},
         "content": [{"type": "text", "text": "نص", "marks": [{"type": "link", "attrs": {"href": "javascript:x"}}]}]},
    ]}
    clean = sanitize_doc(dirty)
    assert clean["content"][0]["type"] == "paragraph"
    assert clean["content"][1]["attrs"] == {"dir": "rtl"}
    assert "marks" not in clean["content"][1]["content"][0]


def test_arabic_pattern_ignores_marks_and_unifies_letter_forms():
    from nis.text import arabic_pattern

    text = "قالَ إنّ الحياةَ قصيرةٌ، ثمّ إنتهى في عام ١٩٥٨ والمدرسـة."
    def hits(q, **kw):
        return [m.group() for m in arabic_pattern(q, **kw).finditer(text)]
    assert hits("الحياة") == ["الحياةَ"]                   # trailing fatha stays inside the match
    assert hits("قصيره") == ["قصيرةٌ"]                     # ه/ة unified, tanween skipped
    assert hits("1958") == ["١٩٥٨"]                        # Western ↔ Eastern digits
    assert hits("المدرسة") == ["المدرسـة"]                 # tatweel skipped
    assert hits("ان", whole_word=True) == ["إنّ"]          # not inside «إنتهى»
    assert hits("ان", unify_letters=False) == []           # strict letter forms
    assert hits("الحياةَ", ignore_marks=False) == ["الحياةَ"]
    assert arabic_pattern("   ") is None
    assert hits("(.*)+") == []                              # user input is literal, never a regex
