"""Stylometric fingerprint (SK08 / FR18) from author-owned samples only.

Only aggregate features and sample hashes are stored — never the sample text. Profiles are erasable.
Samples declared as third-party, unknown, or intended to imitate a living author are refused (AT18).
"""

from __future__ import annotations

import statistics
from collections import Counter
from typing import Any

from ..text import count_words, normalize_ar, sentences, words

ALLOWED_RIGHTS = {"own_work", "licensed_with_permission"}
FUNCTION_WORDS = ["في", "من", "على", "الى", "عن", "ان", "لا", "ما", "ثم", "قد", "كان", "هذا", "التي", "الذي",
                  "كل", "بين", "حتى", "لم", "او", "مع", "عند", "بعد", "قبل", "لكن"]
PUNCT = {"comma": "،", "period": ".", "question": "؟", "exclaim": "!", "ellipsis": "…", "colon": ":",
         "semicolon": "؛", "quote": "«"}
LABELS = {
    "mean_sentence_words": "متوسط طول الجملة", "sentence_cv": "تنوع أطوال الجمل",
    "mean_word_chars": "متوسط طول الكلمة", "ttr": "ثراء المعجم", "wa_start": "افتتاح الجمل بالواو/الفاء",
    "dialogue_share": "نسبة الحوار",
    **{f"p_{k}": f"كثافة «{v}»" for k, v in PUNCT.items()},
}


def extract_features(text: str) -> dict[str, Any]:
    ws = words(text)
    n = len(ws) or 1
    sl = [count_words(s) for s in sentences(text)]
    sl = [x for x in sl if x] or [0]
    mean = statistics.mean(sl)
    norm = [normalize_ar(w) for w in ws]
    window = norm[:5000]
    feats: dict[str, Any] = {
        "words": len(ws),
        "mean_sentence_words": round(mean, 2),
        "sentence_cv": round(statistics.pstdev(sl) / mean, 3) if mean else 0,
        "mean_word_chars": round(sum(len(w) for w in ws) / n, 2),
        "ttr": round(len(set(window)) / (len(window) or 1), 3),
        "wa_start": round(sum(1 for s in sentences(text) if s[:1] in ("و", "ف")) / (len(sl) or 1), 3),
        "dialogue_share": round(text.count("«") / max(1, len(sl)), 3),
    }
    for k, ch in PUNCT.items():
        feats[f"p_{k}"] = round(1000 * text.count(ch) / n, 2)
    fw = Counter(w for w in norm if w in FUNCTION_WORDS)
    feats["function_words"] = {w: round(1000 * fw[w] / n, 2) for w in FUNCTION_WORDS}
    return feats


def merge_features(samples: list[dict[str, Any]]) -> dict[str, Any]:
    keys = [k for k in samples[0] if k not in ("function_words", "words")]
    out: dict[str, Any] = {"words": sum(s["words"] for s in samples)}
    for k in keys:
        vals = [s[k] for s in samples]
        out[k] = round(statistics.mean(vals), 3)
        out[f"{k}__sd"] = round(statistics.pstdev(vals), 3) if len(vals) > 1 else None
    out["function_words"] = {
        w: round(statistics.mean(s["function_words"][w] for s in samples), 2) for w in FUNCTION_WORDS
    }
    return out


def compare_features(base: dict[str, Any], cur: dict[str, Any], threshold: float = 0.35) -> list[dict[str, Any]]:
    """Relative deviations above `threshold`, largest first. Pure description — not a quality verdict."""
    devs = []
    for k, label in LABELS.items():
        b, c = base.get(k), cur.get(k)
        if not isinstance(b, (int, float)) or not isinstance(c, (int, float)) or b == 0:
            continue
        rel = (c - b) / abs(b)
        if abs(rel) >= threshold:
            devs.append({"feature": k, "label": label, "baseline": b, "value": c, "relative": round(rel, 2)})
    return sorted(devs, key=lambda d: abs(d["relative"]), reverse=True)
