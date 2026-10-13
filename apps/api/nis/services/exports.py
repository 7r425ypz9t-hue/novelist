"""Manuscript compilation and publishing formats: DOCX · PDF · EPUB 3 · Markdown (FR20).

All renderers consume the same compiled, sanitized block stream, so Arabic handling is uniform.
"""

from __future__ import annotations

import html
import io
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Document, Manuscript, Project
from .manuscript import ordered_nodes

FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
FONT_NAME = "Noto Naskh Arabic"
SCENE_BREAK = "⁂"
AR_DIGITS = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")


@dataclass
class Item:
    kind: str  # title | part | chapter | block | scene_break | notes
    text: str = ""
    node: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


@dataclass
class Book:
    title: str
    subtitle: str
    author: str
    language: str
    items: list[Item]

    @property
    def chapters(self) -> list[str]:
        return [i.text for i in self.items if i.kind in ("chapter", "part")]


def compile_book(db: Session, project: Project, manuscript: Manuscript | None = None) -> Book:
    if manuscript is None:
        manuscript = db.scalar(select(Manuscript).where(Manuscript.project_id == project.id)
                               .order_by(Manuscript.position))
    items: list[Item] = []
    if manuscript is None:
        return Book(project.title, "", "", project.language, items)
    nodes = ordered_nodes(db, manuscript.id)
    docs = {d.node_id: d for d in db.scalars(select(Document).where(Document.project_id == project.id))}
    ch_no = 0
    notes: list[str] = []
    prev_scene_in_chapter = False

    def close_chapter() -> None:
        nonlocal notes
        if notes:
            items.append(Item("notes", notes=list(notes)))
        notes = []

    for n in nodes:
        if n.type == "part":
            close_chapter()
            items.append(Item("part", n.title or "جزء"))
            continue
        if n.type == "chapter":
            close_chapter()
            ch_no += 1
            items.append(Item("chapter", n.title or f"الفصل {ch_no}"))
            prev_scene_in_chapter = False
        elif n.type == "scene":
            if prev_scene_in_chapter:
                items.append(Item("scene_break", SCENE_BREAK))
            prev_scene_in_chapter = True
        d = docs.get(n.id)
        if not d:
            continue
        for block in d.content_json.get("content") or []:
            if _is_empty(block):
                continue
            items.append(Item("block", node=_collect_notes(block, notes)))
    close_chapter()
    return Book(manuscript.title or project.title, manuscript.subtitle, manuscript.author_name,
                project.language, items)


def _is_empty(block: dict[str, Any]) -> bool:
    return block.get("type") in ("paragraph", "heading") and not block.get("content")


def _collect_notes(block: dict[str, Any], notes: list[str]) -> dict[str, Any]:
    """Number footnote marks per chapter; the note text is stored on the node as `_fn`."""
    import copy

    b = copy.deepcopy(block)

    def walk(n: dict[str, Any]) -> None:
        for m in n.get("marks") or []:
            if m.get("type") == "footnote" and (m.get("attrs") or {}).get("note"):
                notes.append(m["attrs"]["note"])
                n["_fn"] = len(notes)
        for c in n.get("content") or []:
            walk(c)

    walk(b)
    return b


def runs(block: dict[str, Any]) -> list[tuple[str, set[str], int | None]]:
    """Flatten a block into (text, marks, footnote_no) runs."""
    out: list[tuple[str, set[str], int | None]] = []

    def walk(n: dict[str, Any]) -> None:
        if n.get("type") == "text":
            out.append((n.get("text", ""), {m["type"] for m in n.get("marks") or []}, n.get("_fn")))
        elif n.get("type") == "hardBreak":
            out.append(("\n", set(), None))
        else:
            kids = n.get("content") or []
            for i, c in enumerate(kids):
                walk(c)
                if n.get("type") in ("blockquote", "bulletList", "orderedList", "listItem") and i < len(kids) - 1:
                    out.append(("\n", set(), None))

    walk(block)
    return out


def plain(block: dict[str, Any]) -> str:
    return "".join(t for t, _, _ in runs(block))


# ───────────────────────────── DOCX ─────────────────────────────


def to_docx(book: Book) -> bytes:
    import docx
    from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Pt, RGBColor

    d = docx.Document()
    rtl = book.language.startswith("ar")

    def set_run_fonts(rpr_parent, size_pt: float, bold: bool = False) -> None:
        rpr = rpr_parent.get_or_add_rPr()
        fonts = rpr.find(qn("w:rFonts"))
        if fonts is None:
            fonts = OxmlElement("w:rFonts")
            rpr.insert(0, fonts)
        for attr in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
            fonts.set(qn(attr), FONT_NAME)
        for tag in ("w:sz", "w:szCs"):
            el = rpr.find(qn(tag))
            if el is None:
                el = OxmlElement(tag)
                rpr.append(el)
            el.set(qn("w:val"), str(int(size_pt * 2)))
        if bold:
            rpr.append(OxmlElement("w:bCs"))
        if rtl:
            rpr.append(OxmlElement("w:rtl"))
        lang = OxmlElement("w:lang")
        lang.set(qn("w:bidi"), "ar-SA")
        rpr.append(lang)

    def bidi(p) -> None:
        if rtl:
            p._p.get_or_add_pPr().insert(0, OxmlElement("w:bidi"))

    normal = d.styles["Normal"]
    normal.font.name = FONT_NAME
    normal.font.size = Pt(13)
    set_run_fonts(normal.element, 13)
    for name, size in (("Title", 28), ("Heading 1", 20), ("Heading 2", 16)):
        st = d.styles[name]
        st.font.name = FONT_NAME
        st.font.size = Pt(size)
        st.font.color.rgb = RGBColor(0x1F, 0x4E, 0x79)
        set_run_fonts(st.element, size, bold=True)
    if rtl:
        sect = d.sections[0]._sectPr
        sect.append(OxmlElement("w:bidi"))
    settings = d.settings.element
    upd = OxmlElement("w:updateFields")
    upd.set(qn("w:val"), "true")
    settings.append(upd)

    def para(text: str = "", style: str | None = None, align=None):
        p = d.add_paragraph(style=style)
        bidi(p)
        if align is not None:
            p.alignment = align
        if text:
            r = p.add_run(text)
            set_run_fonts(r._r, 13)
        return p

    # title page
    p = d.add_paragraph(style="Title")
    bidi(p)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run(book.title)
    if book.subtitle:
        para(book.subtitle, align=WD_ALIGN_PARAGRAPH.CENTER)
    if book.author:
        para(book.author, align=WD_ALIGN_PARAGRAPH.CENTER)
    d.paragraphs[-1].add_run().add_break(WD_BREAK.PAGE)

    # table of contents: a real TOC field (Word refreshes it on open) + a static fallback list
    h = d.add_paragraph(style="Heading 1")
    bidi(h)
    h.add_run("المحتويات")
    tp = d.add_paragraph()
    bidi(tp)
    r = tp.add_run()
    fld_begin = OxmlElement("w:fldChar")
    fld_begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = 'TOC \\o "1-2" \\h \\z \\u'
    fld_sep = OxmlElement("w:fldChar")
    fld_sep.set(qn("w:fldCharType"), "separate")
    fld_end = OxmlElement("w:fldChar")
    fld_end.set(qn("w:fldCharType"), "end")
    r._r.append(fld_begin)
    r._r.append(instr)
    r._r.append(fld_sep)
    for t in book.chapters:
        rr = tp.add_run(t)
        set_run_fonts(rr._r, 13)
        rr.add_break()
    tp.add_run()._r.append(fld_end)

    for it in book.items:
        if it.kind in ("part", "chapter"):
            hp = d.add_paragraph(style="Heading 1" if it.kind == "part" else "Heading 2")
            bidi(hp)
            hp.alignment = WD_ALIGN_PARAGRAPH.CENTER
            hp.paragraph_format.page_break_before = True
            hp.add_run(it.text)
        elif it.kind == "scene_break":
            para(SCENE_BREAK, align=WD_ALIGN_PARAGRAPH.CENTER)
        elif it.kind == "notes":
            para("—" * 6, align=WD_ALIGN_PARAGRAPH.RIGHT if rtl else WD_ALIGN_PARAGRAPH.LEFT)
            for i, note in enumerate(it.notes, start=1):
                np_ = para()
                r1 = np_.add_run(f"({str(i).translate(AR_DIGITS) if rtl else i}) ")
                set_run_fonts(r1._r, 10.5)
                r2 = np_.add_run(note)
                set_run_fonts(r2._r, 10.5)
        elif it.kind == "block":
            b = it.node
            style = None
            if b.get("type") == "heading":
                style = "Heading 2"
            p = d.add_paragraph(style=style)
            bidi(p)
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY if b.get("type") == "paragraph" else None
            if b.get("type") == "blockquote":
                p.paragraph_format.left_indent = Pt(24)
                p.paragraph_format.right_indent = Pt(24)
            for text, marks, fn in runs(b):
                if text == "\n":
                    p.add_run().add_break()
                    continue
                rr = p.add_run(text)
                set_run_fonts(rr._r, 13)
                rr.bold = "bold" in marks or None
                rr.italic = "italic" in marks or None
                rr.underline = "underline" in marks or None
                if "strike" in marks:
                    rr.font.strike = True
                if fn:
                    sup = p.add_run(str(fn).translate(AR_DIGITS) if rtl else str(fn))
                    sup.font.superscript = True
                    set_run_fonts(sup._r, 9)
    buf = io.BytesIO()
    d.core_properties.title = book.title
    d.core_properties.author = book.author or ""
    d.core_properties.language = book.language
    d.save(buf)
    return buf.getvalue()


# ───────────────────────────── PDF ─────────────────────────────


def _pdf_fonts() -> tuple[str, str]:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    if "NIS-Naskh" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("NIS-Naskh", str(FONT_DIR / "NotoNaskhArabic-Regular.ttf")))
        pdfmetrics.registerFont(TTFont("NIS-Naskh-Bold", str(FONT_DIR / "NotoNaskhArabic-Bold.ttf")))
    return "NIS-Naskh", "NIS-Naskh-Bold"


def _shape(text: str) -> str:
    """Contextual shaping + bidi reordering. ReportLab has no mark positioning (GPOS), so optional tashkeel is
    dropped in PDF only (DOCX/EPUB keep it) — documented limitation."""
    import arabic_reshaper
    from bidi.algorithm import get_display

    return get_display(arabic_reshaper.reshape(text), base_dir="R")


def _wrap(text: str, font: str, size: float, width: float) -> list[str]:
    from reportlab.pdfbase.pdfmetrics import stringWidth

    lines: list[str] = []
    for hard in text.split("\n"):
        words_ = hard.split()
        cur: list[str] = []
        for w in words_:
            trial = " ".join([*cur, w])
            if cur and stringWidth(_shape(trial), font, size) > width:
                lines.append(" ".join(cur))
                cur = [w]
            else:
                cur.append(w)
        lines.append(" ".join(cur))
    return lines


def to_pdf(book: Book) -> bytes:
    """Prefer the HarfBuzz/Pango engine (full tashkeel, real footnotes); fall back to ReportLab."""
    try:
        import weasyprint  # noqa: F401
    except (ImportError, OSError):
        return to_pdf_reportlab(book)
    from .pdf_html import to_pdf_html

    return to_pdf_html(book)


def to_pdf_reportlab(book: Book) -> bytes:
    from reportlab.lib.pagesizes import A5
    from reportlab.lib.units import mm
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from reportlab.pdfgen import canvas

    reg, bold = _pdf_fonts()
    W, H = A5
    ml, mr, mt, mb = 18 * mm, 18 * mm, 20 * mm, 22 * mm
    tw = W - ml - mr
    body, lead = 11.5, 11.5 * 1.95

    # layout pass → pages of draw ops: (kind, text, font, size, y, extra)
    pages: list[list[tuple]] = [[]]
    y = H - mt
    toc: list[tuple[str, int, str]] = []

    def new_page() -> None:
        nonlocal y
        pages.append([])
        y = H - mt

    def need(h: float) -> None:
        if y - h < mb:
            new_page()

    for it in book.items:
        if it.kind in ("part", "chapter"):
            if pages[-1]:
                new_page()
            y -= 30 * mm if it.kind == "part" else 18 * mm
            size = 20 if it.kind == "part" else 16
            for ln in _wrap(it.text, bold, size, tw):
                pages[-1].append(("center", ln, bold, size, y))
                y -= size * 1.8
            y -= 8 * mm
            key = f"c{len(toc)}"
            toc.append((it.text, len(pages) - 1, key))
            pages[-1].append(("bookmark", it.text, key, it.kind, y))
        elif it.kind == "scene_break":
            need(lead * 2)
            y -= lead * 0.4
            pages[-1].append(("center", "*   *   *", reg, body, y))  # ⁂ is not in the embedded font
            y -= lead * 1.2
        elif it.kind == "notes":
            need(lead * 2)
            pages[-1].append(("rule", "", reg, body, y))
            y -= lead * 0.8
            for i, note in enumerate(it.notes, start=1):
                for j, ln in enumerate(_wrap(f"({str(i).translate(AR_DIGITS)}) {note}", reg, 9.5, tw)):
                    need(9.5 * 1.8)
                    pages[-1].append(("right", ln, reg, 9.5, y))
                    y -= 9.5 * 1.8
                    _ = j
        elif it.kind == "block":
            b = it.node
            is_head = b.get("type") == "heading"
            font, size = (bold, 13.5) if is_head else (reg, body)
            txt = ""
            for t, marks, fn in runs(b):
                txt += t + (f"[{str(fn).translate(AR_DIGITS)}]" if fn else "")
                _ = marks
            indent = 10 * mm if b.get("type") == "blockquote" else 0
            lines = _wrap(txt, font, size, tw - 2 * indent)
            for k, ln in enumerate(lines):
                need(size * 1.95)
                last = k == len(lines) - 1
                pages[-1].append(("center" if is_head else ("right" if last else "justify"), ln, font, size, y, indent))
                y -= size * 1.95
            y -= lead * 0.35

    # TOC pages
    per_toc = int((H - mt - mb - 20 * mm) // (lead * 1.2))
    toc_pages = max(1, -(-len(toc) // per_toc)) if toc else 0
    offset = 1 + toc_pages  # title page + toc pages

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A5, pageCompression=1)
    c.setTitle(book.title)
    c.setAuthor(book.author or "")
    c.setSubject("Novel Intelligence Studio export")

    def draw_center(text: str, font: str, size: float, yy: float) -> None:
        s = _shape(text)
        c.setFont(font, size)
        c.drawString((W - stringWidth(s, font, size)) / 2, yy, s)

    # title page
    draw_center(book.title, bold, 24, H * 0.62)
    if book.subtitle:
        draw_center(book.subtitle, reg, 14, H * 0.62 - 14 * mm)
    if book.author:
        draw_center(book.author, reg, 13, H * 0.35)
    c.showPage()
    # toc
    for tp in range(toc_pages):
        yy = H - mt - 10 * mm
        if tp == 0:
            draw_center("المحتويات", bold, 16, yy)
            yy -= 14 * mm
        for title, page_idx, key in toc[tp * per_toc:(tp + 1) * per_toc]:
            pno = str(page_idx + 1 + offset).translate(AR_DIGITS)
            s = _shape(title)
            c.setFont(reg, body)
            c.drawRightString(W - mr, yy, s)
            c.drawString(ml, yy, pno)
            c.linkRect("", key, (ml, yy - 3, W - mr, yy + body), relative=0)
            yy -= lead * 1.2
        c.showPage()
    # content
    for pi, ops in enumerate(pages):
        if not ops:
            continue
        for op in ops:
            kind = op[0]
            if kind == "bookmark":
                _, title, key, level, _yy = op
                c.bookmarkPage(key)
                c.addOutlineEntry(title, key, level=0 if level == "part" else 1 if any(
                    i.kind == "part" for i in book.items) else 0)
                continue
            _, text, font, size, yy, *rest = op
            if kind == "rule":
                c.setLineWidth(0.4)
                c.line(W - mr - tw / 3, yy, W - mr, yy)
                continue
            indent = rest[0] if rest else 0
            s = _shape(text)
            c.setFont(font, size)
            if kind == "center":
                c.drawString((W - stringWidth(s, font, size)) / 2, yy, s)
            elif kind == "right" or " " not in s:
                c.drawRightString(W - mr - indent, yy, s)
            else:
                parts = s.split(" ")
                widths = [stringWidth(p, font, size) for p in parts]
                gap = (tw - 2 * indent - sum(widths)) / max(1, len(parts) - 1)
                if gap > size * 1.2:  # avoid ugly rivers on short lines
                    c.drawRightString(W - mr - indent, yy, s)
                else:
                    x = ml + indent
                    for p, w in zip(parts, widths, strict=True):
                        c.drawString(x, yy, p)
                        x += w + gap
        c.setFont(reg, 9)
        c.drawCentredString(W / 2, mb / 2, str(pi + 1 + offset).translate(AR_DIGITS))
        c.showPage()
    c.save()
    return buf.getvalue()


# ───────────────────────────── EPUB 3 ─────────────────────────────


def _xhtml_inline(block: dict[str, Any]) -> str:
    out = []
    for text, marks, fn in runs(block):
        if text == "\n":
            out.append("<br/>")
            continue
        t = html.escape(text)
        if "bold" in marks:
            t = f"<strong>{t}</strong>"
        if "italic" in marks:
            t = f"<em>{t}</em>"
        if "underline" in marks:
            t = f"<u>{t}</u>"
        if "strike" in marks:
            t = f"<s>{t}</s>"
        if fn:
            t += f'<sup><a epub:type="noteref" href="#fn{fn}" id="ref{fn}">{fn}</a></sup>'
        out.append(t)
    return "".join(out)


def to_epub(book: Book, book_id: str | None = None) -> bytes:
    rtl = book.language.startswith("ar")
    dir_ = "rtl" if rtl else "ltr"
    uid = book_id or f"urn:uuid:{uuid.uuid4()}"
    # split into chapter files
    chapters: list[tuple[str, list[str]]] = []
    cur_title, cur_body = book.title, []
    for it in book.items:
        if it.kind in ("part", "chapter"):
            if cur_body or chapters:
                chapters.append((cur_title, cur_body))
            cur_title, cur_body = it.text, [f"<h{1 if it.kind == 'part' else 2}>{html.escape(it.text)}</h{1 if it.kind == 'part' else 2}>"]
        elif it.kind == "scene_break":
            cur_body.append(f'<p class="break">{SCENE_BREAK}</p>')
        elif it.kind == "notes":
            notes = "".join(
                f'<aside epub:type="footnote" id="fn{i}"><p><a href="#ref{i}">{i}</a>. {html.escape(n)}</p></aside>'
                for i, n in enumerate(it.notes, start=1)
            )
            cur_body.append(f'<section class="notes">{notes}</section>')
        elif it.kind == "block":
            b = it.node
            t = b.get("type")
            inner = _xhtml_inline(b)
            if t == "heading":
                cur_body.append(f"<h3>{inner}</h3>")
            elif t == "blockquote":
                cur_body.append(f"<blockquote><p>{inner}</p></blockquote>")
            elif t == "horizontalRule":
                cur_body.append("<hr/>")
            else:
                cur_body.append(f"<p>{inner}</p>")
    chapters.append((cur_title, cur_body))

    def page(title: str, body: str) -> str:
        return (
            '<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
            f'<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" '
            f'lang="{book.language}" xml:lang="{book.language}" dir="{dir_}">\n'
            f'<head><meta charset="utf-8"/><title>{html.escape(title)}</title>'
            '<link rel="stylesheet" type="text/css" href="style.css"/></head>\n'
            f'<body dir="{dir_}">{body}</body></html>'
        )

    css = (
        '@font-face{font-family:"Noto Naskh Arabic";src:url(fonts/NotoNaskhArabic-Regular.ttf);}\n'
        '@font-face{font-family:"Noto Naskh Arabic";font-weight:bold;src:url(fonts/NotoNaskhArabic-Bold.ttf);}\n'
        f'body{{font-family:"Noto Naskh Arabic",serif;direction:{dir_};text-align:justify;line-height:1.9;}}\n'
        "h1,h2{text-align:center;margin:2em 0 1em;}p{text-indent:1.2em;margin:0 0 .4em;}"
        "p.break{text-align:center;text-indent:0;margin:1em 0;}blockquote{margin:1em 2em;}"
        ".notes{font-size:.85em;border-top:1px solid #999;margin-top:2em;}"
    )
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    files = [(f"chap{i:03d}.xhtml", t, b) for i, (t, b) in enumerate(chapters, start=1)]
    nav_items = "".join(f'<li><a href="{f}">{html.escape(t)}</a></li>' for f, t, _ in files)
    nav = page("المحتويات", f'<nav epub:type="toc" id="toc"><h1>المحتويات</h1><ol>{nav_items}</ol></nav>')
    title_page = page(book.title, f'<section epub:type="titlepage" style="text-align:center;margin-top:30%">'
                                  f"<h1>{html.escape(book.title)}</h1>"
                                  f"<p>{html.escape(book.subtitle)}</p><p>{html.escape(book.author)}</p></section>")
    manifest = "".join(
        f'<item id="c{i}" href="{f}" media-type="application/xhtml+xml"/>' for i, (f, _, _) in enumerate(files)
    )
    spine = "".join(f'<itemref idref="c{i}"/>' for i in range(len(files)))
    opf = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid" '
        f'xml:lang="{book.language}" dir="{dir_}">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        f'<dc:identifier id="bookid">{html.escape(uid)}</dc:identifier>'
        f"<dc:title>{html.escape(book.title)}</dc:title><dc:language>{book.language}</dc:language>"
        f"<dc:creator>{html.escape(book.author or 'مجهول')}</dc:creator>"
        f'<meta property="dcterms:modified">{now}</meta></metadata>'
        '<manifest><item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
        '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>'
        '<item id="title" href="title.xhtml" media-type="application/xhtml+xml"/>'
        '<item id="css" href="style.css" media-type="text/css"/>'
        '<item id="f1" href="fonts/NotoNaskhArabic-Regular.ttf" media-type="font/ttf"/>'
        '<item id="f2" href="fonts/NotoNaskhArabic-Bold.ttf" media-type="font/ttf"/>'
        f"{manifest}</manifest>"
        f'<spine toc="ncx" page-progression-direction="{dir_}"><itemref idref="title"/><itemref idref="nav"/>{spine}</spine>'
        "</package>"
    )
    ncx_points = "".join(
        f'<navPoint id="n{i}" playOrder="{i + 1}"><navLabel><text>{html.escape(t)}</text></navLabel>'
        f'<content src="{f}"/></navPoint>' for i, (f, t, _) in enumerate(files)
    )
    ncx = (
        '<?xml version="1.0" encoding="utf-8"?><ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">'
        f'<head><meta name="dtb:uid" content="{html.escape(uid)}"/></head>'
        f"<docTitle><text>{html.escape(book.title)}</text></docTitle><navMap>{ncx_points}</navMap></ncx>"
    )
    container = (
        '<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
        "</rootfiles></container>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", container, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/content.opf", opf, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/nav.xhtml", nav, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/toc.ncx", ncx, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/title.xhtml", title_page, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/style.css", css, compress_type=zipfile.ZIP_DEFLATED)
        for f in ("NotoNaskhArabic-Regular.ttf", "NotoNaskhArabic-Bold.ttf"):
            z.write(FONT_DIR / f, f"OEBPS/fonts/{f}", compress_type=zipfile.ZIP_DEFLATED)
        for f, t, b in files:
            z.writestr(f"OEBPS/{f}", page(t, "".join(b)), compress_type=zipfile.ZIP_DEFLATED)
    return buf.getvalue()


# ───────────────────────────── Markdown ─────────────────────────────


def to_markdown(book: Book) -> bytes:
    lines = [f"# {book.title}", ""]
    if book.subtitle:
        lines += [f"## {book.subtitle}", ""]
    for it in book.items:
        if it.kind == "part":
            lines += [f"# {it.text}", ""]
        elif it.kind == "chapter":
            lines += [f"## {it.text}", ""]
        elif it.kind == "scene_break":
            lines += [SCENE_BREAK, ""]
        elif it.kind == "notes":
            lines += [f"[^{i}]: {n}" for i, n in enumerate(it.notes, start=1)] + [""]
        else:
            txt = "".join(t + (f"[^{fn}]" if fn else "") for t, _, fn in runs(it.node))
            prefix = "> " if it.node.get("type") == "blockquote" else ("### " if it.node.get("type") == "heading" else "")
            lines += [prefix + txt, ""]
    return "\n".join(lines).encode("utf-8")


RENDERERS = {"docx": to_docx, "pdf": to_pdf, "epub": to_epub, "md": to_markdown}
MEDIA = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pdf": "application/pdf",
    "epub": "application/epub+zip",
    "md": "text/markdown; charset=utf-8",
    "zip": "application/zip",
}
