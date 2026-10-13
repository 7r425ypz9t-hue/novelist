"""Arabic text processing and Tiptap/ProseMirror document helpers.

Word-count definition (documented in docs/SPEC_REVIEW.md §4): a word is a maximal run of letters/digits
(Arabic or Latin) after removing tashkeel and tatweel; attached clitics (و، ف، ب، ال) do not split a word;
numbers count as one word; punctuation never counts.
"""

from __future__ import annotations

import copy
import difflib
import re
from typing import Any

TASHKEEL = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭ]")
TATWEEL = "ـ"
WORD_RE = re.compile(r"[^\W_]+(?:['’][^\W_]+)*", re.UNICODE)
SENTENCE_END = re.compile(r"(?<=[\.\!\?؟…؛])\s+|\n+")
ARABIC_CHAR = re.compile(r"[؀-ۿ]")

_NORM_MAP = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ة": "ه", "ؤ": "و", "ئ": "ي"})
_EASTERN_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")

_STOP_RAW = """في من على الى إلى عن مع ان أن إن او أو ثم لا لم لن ما هذا هذه ذلك تلك التي الذي الذين كان كانت
    قد كل بعد قبل عند حتى هو هي هم هن انا أنا نحن انت أنت و ف ب ل يا بين اذا إذا لكن لقد غير كما
    متى ماذا لماذا كيف أين اين هل كم أي اي ما منذ the a an of in on at to is was were and or what when who"""
_PREFIXES = ("وال", "فال", "بال", "كال", "لل", "ال", "و")
_SUFFIXES = ("ها", "ات", "ون", "ين", "ان", "يه", "يه", "ه", "ي")


def _norm_stop(w: str) -> str:
    return TASHKEEL.sub("", w).replace(TATWEEL, "").translate(_NORM_MAP).lower()


STOPWORDS = {_norm_stop(w) for w in _STOP_RAW.split()}


def strip_diacritics(s: str) -> str:
    return TASHKEEL.sub("", s).replace(TATWEEL, "")


def normalize_ar(s: str) -> str:
    """Search normalization: no diacritics, unified alef/yaa/taa-marbuta, western digits, lowercase."""
    return strip_diacritics(s).translate(_NORM_MAP).translate(_EASTERN_DIGITS).lower()


def words(s: str) -> list[str]:
    return WORD_RE.findall(strip_diacritics(s))


def count_words(s: str) -> int:
    return len(words(s))


def light_stem(tok: str) -> str:
    if not ARABIC_CHAR.search(tok):
        return tok
    for p in _PREFIXES:
        if tok.startswith(p) and len(tok) - len(p) >= 3:
            tok = tok[len(p):]
            break
    for suf in _SUFFIXES:
        if tok.endswith(suf) and len(tok) - len(suf) >= 3:
            tok = tok[: -len(suf)]
            break
    return tok


def search_tokens(s: str) -> list[str]:
    out = []
    for w in WORD_RE.findall(normalize_ar(s)):
        if w in STOPWORDS or len(w) < 2:
            continue
        out.append(light_stem(w))
    return out


def sentences(s: str) -> list[str]:
    return [x.strip() for x in SENTENCE_END.split(s) if x and x.strip()]


def is_arabic(s: str) -> bool:
    letters = [c for c in s if c.isalpha()]
    if not letters:
        return False
    return sum(1 for c in letters if ARABIC_CHAR.match(c)) / len(letters) > 0.5


# ───────────────────────────── Tiptap JSON ─────────────────────────────

ALLOWED_NODES = {
    "doc", "paragraph", "heading", "blockquote", "bulletList", "orderedList", "listItem",
    "hardBreak", "horizontalRule", "text",
}
ALLOWED_MARKS = {"bold", "italic", "underline", "strike", "footnote", "highlight"}
ALLOWED_ATTRS = {"level", "textAlign", "dir", "note", "start"}
INLINE_BLOCKS = {"paragraph", "heading"}


def empty_doc() -> dict[str, Any]:
    return {"type": "doc", "content": [{"type": "paragraph"}]}


def sanitize_doc(node: Any, depth: int = 0) -> dict[str, Any]:
    """Whitelist node types, marks and attributes (stored-XSS defence for every renderer/export)."""
    if depth > 40 or not isinstance(node, dict):
        return {"type": "paragraph"}
    t = node.get("type")
    if t not in ALLOWED_NODES:
        t = "paragraph"
    out: dict[str, Any] = {"type": t}
    attrs = {k: v for k, v in (node.get("attrs") or {}).items()
             if k in ALLOWED_ATTRS and isinstance(v, (str, int, float, type(None)))}
    if t == "heading":
        lvl = attrs.get("level", 2)
        attrs["level"] = lvl if lvl in (1, 2, 3) else 2
    if "dir" in attrs and attrs["dir"] not in ("rtl", "ltr", "auto", None):
        attrs.pop("dir")
    if attrs:
        out["attrs"] = attrs
    if t == "text":
        out["text"] = str(node.get("text", ""))[:200_000]
        marks = []
        for m in node.get("marks") or []:
            if isinstance(m, dict) and m.get("type") in ALLOWED_MARKS:
                mm: dict[str, Any] = {"type": m["type"]}
                ma = {k: str(v)[:4000] for k, v in (m.get("attrs") or {}).items() if k in ALLOWED_ATTRS and v}
                if ma:
                    mm["attrs"] = ma
                marks.append(mm)
        if marks:
            out["marks"] = marks
        return out
    children = node.get("content")
    if isinstance(children, list):
        kids = [sanitize_doc(c, depth + 1) for c in children]
        kids = [k for k in kids if not (k["type"] == "text" and not k.get("text"))]
        if kids:
            out["content"] = kids
    if t == "doc" and not out.get("content"):
        out["content"] = [{"type": "paragraph"}]
    return out


def _node_text(node: dict[str, Any]) -> str:
    t = node.get("type")
    if t == "text":
        return node.get("text", "")
    if t == "hardBreak":
        return "\n"
    parts = [_node_text(c) for c in node.get("content") or []]
    if t in INLINE_BLOCKS or t == "listItem":
        return "".join(parts) if t in INLINE_BLOCKS else "\n".join(parts)
    return "\n".join(p for p in parts)


def blocks(doc: dict[str, Any]) -> list[dict[str, Any]]:
    """Top-level blocks with their plain text and inline-editability."""
    out = []
    for i, n in enumerate(doc.get("content") or []):
        out.append({"index": i, "type": n.get("type"), "text": _node_text(n), "editable": n.get("type") in INLINE_BLOCKS})
    return out


def doc_to_plain(doc: dict[str, Any]) -> str:
    return "\n\n".join(b["text"] for b in blocks(doc))


def block_offsets(doc: dict[str, Any]) -> list[tuple[int, int]]:
    """(start, end) offsets of each top-level block inside doc_to_plain(doc)."""
    pos, out = 0, []
    for b in blocks(doc):
        out.append((pos, pos + len(b["text"])))
        pos += len(b["text"]) + 2
    return out


def locate(doc: dict[str, Any], global_start: int) -> tuple[int, int]:
    """Map a plain-text offset to (block_index, offset_in_block)."""
    for i, (s, e) in enumerate(block_offsets(doc)):
        if s <= global_start <= e:
            return i, global_start - s
    return max(0, len(doc.get("content") or []) - 1), 0


def doc_from_plain(text: str, heading_first: bool = False) -> dict[str, Any]:
    paras = [p.strip("\n") for p in re.split(r"\n\s*\n", text.replace("\r\n", "\n")) if p.strip()]
    content: list[dict[str, Any]] = []
    for i, p in enumerate(paras):
        node: dict[str, Any] = {"type": "paragraph", "content": [{"type": "text", "text": p}]}
        if heading_first and i == 0:
            node = {"type": "heading", "attrs": {"level": 2}, "content": [{"type": "text", "text": p}]}
        content.append(node)
    return {"type": "doc", "content": content or [{"type": "paragraph"}]}


def _split_inline(nodes: list[dict[str, Any]], offset: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    left: list[dict[str, Any]] = []
    right: list[dict[str, Any]] = []
    pos = 0
    for n in nodes:
        ln = len(n.get("text", "")) if n.get("type") == "text" else 1
        if pos + ln <= offset:
            left.append(n)
        elif pos >= offset:
            right.append(n)
        else:
            cut = offset - pos
            a, b = copy.deepcopy(n), copy.deepcopy(n)
            a["text"], b["text"] = n["text"][:cut], n["text"][cut:]
            left.append(a)
            right.append(b)
        pos += ln
    return left, right


def _merge_text(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Join adjacent text nodes that carry identical marks (keeps documents compact after patches)."""
    out: list[dict[str, Any]] = []
    for n in nodes:
        if out and n.get("type") == "text" and out[-1].get("type") == "text" and out[-1].get("marks") == n.get("marks"):
            out[-1] = {**out[-1], "text": out[-1]["text"] + n["text"]}
        else:
            out.append(n)
    return out


class PatchMismatch(Exception):
    """The base text no longer matches what the proposal expected: requires manual merge."""


def apply_ops(doc: dict[str, Any], ops: list[dict[str, Any]]) -> dict[str, Any]:
    """Apply proposal operations. Ops are validated against `expected` text; any mismatch aborts.

    Supported: replace_text{block,start,end,expected,text} · delete_block{block,expected} ·
    insert_block{block,text} (inserted before `block`). Ops apply from the end backwards so indices hold.
    """
    new = copy.deepcopy(doc)
    content = new.setdefault("content", [])

    def key(op: dict[str, Any]) -> tuple[int, int]:
        return (int(op.get("block", 0)), int(op.get("start", 0)))

    for op in sorted(ops, key=key, reverse=True):
        kind, bi = op.get("op"), int(op.get("block", -1))
        if kind == "insert_block":
            if not 0 <= bi <= len(content):
                raise PatchMismatch("موضع الإدراج خارج حدود المستند")
            content.insert(bi, {"type": "paragraph", "content": [{"type": "text", "text": op["text"]}]})
            continue
        if not 0 <= bi < len(content):
            raise PatchMismatch("الفقرة المستهدفة غير موجودة في النسخة الحالية")
        block = content[bi]
        text = _node_text(block)
        if kind == "delete_block":
            if text != op.get("expected", text):
                raise PatchMismatch("نص الفقرة تغيّر منذ إنشاء المقترح")
            del content[bi]
            continue
        if kind != "replace_text":
            raise PatchMismatch(f"عملية غير مدعومة: {kind}")
        if block.get("type") not in INLINE_BLOCKS:
            raise PatchMismatch("لا يمكن تعديل هذا النوع من الكتل نصياً")
        s, e = int(op["start"]), int(op["end"])
        if text[s:e] != op.get("expected", ""):
            raise PatchMismatch("المقطع المستهدف تغيّر منذ إنشاء المقترح")
        inline = block.get("content") or []
        left, rest = _split_inline(inline, s)
        _, right = _split_inline(rest, e - s)
        marks = None
        for n in rest[:1] or left[-1:]:
            marks = n.get("marks")
        mid = []
        if op.get("text"):
            t: dict[str, Any] = {"type": "text", "text": op["text"]}
            if marks:
                t["marks"] = marks
            mid.append(t)
        block["content"] = _merge_text([n for n in left + mid + right if n.get("type") != "text" or n.get("text")])
    if not content:
        content.append({"type": "paragraph"})
    return new


# ───────────────────────────── diff ─────────────────────────────

_TOKEN_RE = re.compile(r"\s+|[^\s]+")


def diff_texts(a: str, b: str) -> list[dict[str, str]]:
    """Paragraph-aligned, word-level diff → [{op: equal|insert|delete, text}]."""
    pa, pb = a.split("\n\n"), b.split("\n\n")
    segs: list[dict[str, str]] = []

    def push(op: str, text: str) -> None:
        if not text:
            return
        if segs and segs[-1]["op"] == op:
            segs[-1]["text"] += text
        else:
            segs.append({"op": op, "text": text})

    sm = difflib.SequenceMatcher(a=pa, b=pb, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            push("equal", "\n\n".join(pa[i1:i2]) + "\n\n")
        elif tag == "delete":
            push("delete", "\n\n".join(pa[i1:i2]) + "\n\n")
        elif tag == "insert":
            push("insert", "\n\n".join(pb[j1:j2]) + "\n\n")
        else:
            ta = _TOKEN_RE.findall("\n\n".join(pa[i1:i2]))
            tb = _TOKEN_RE.findall("\n\n".join(pb[j1:j2]))
            wm = difflib.SequenceMatcher(a=ta, b=tb, autojunk=False)
            for t2, x1, x2, y1, y2 in wm.get_opcodes():
                if t2 == "equal":
                    push("equal", "".join(ta[x1:x2]))
                else:
                    push("delete", "".join(ta[x1:x2]))
                    push("insert", "".join(tb[y1:y2]))
            push("equal", "\n\n")
    if segs and segs[-1]["op"] == "equal" and segs[-1]["text"].endswith("\n\n"):
        segs[-1]["text"] = segs[-1]["text"][:-2]
        if not segs[-1]["text"]:
            segs.pop()
    return segs


def diff_stats(segs: list[dict[str, str]]) -> dict[str, int]:
    return {
        "inserted_words": sum(count_words(s["text"]) for s in segs if s["op"] == "insert"),
        "deleted_words": sum(count_words(s["text"]) for s in segs if s["op"] == "delete"),
    }
