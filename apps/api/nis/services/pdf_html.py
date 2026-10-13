"""High-quality PDF via WeasyPrint (Pango + HarfBuzz): full Arabic shaping *with* tashkeel, kashida-free
justification, real page footnotes, a table of contents with page numbers and PDF bookmarks.

Used automatically when WeasyPrint is installed (`pip install "nis-api[pdf]"`); otherwise `exports.to_pdf`
falls back to the ReportLab renderer.
"""

from __future__ import annotations

import html

from .exports import FONT_DIR, SCENE_BREAK, Book, Item, runs


def _inline(block: dict) -> str:
    out = []
    for text, marks, fn in runs(block):
        if text == "\n":
            out.append("<br>")
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
        out.append(t)
        if fn:
            out.append(f'<span class="fn">{html.escape(block.get("_notes", {}).get(fn, ""))}</span>')
    return "".join(out)


def book_html(book: Book) -> str:
    rtl = book.language.startswith("ar")
    # footnote texts are collected per chapter in compile_book as Item("notes"); map them back by number
    body, toc, notes_buffer, pending_blocks = [], [], [], []

    def flush_chapter():
        for b in pending_blocks:
            b.node["_notes"] = {i: n for i, n in enumerate(notes_buffer, start=1)}
            body.append(_render_block(b.node))
        pending_blocks.clear()
        notes_buffer.clear()

    n = 0
    for it in book.items:
        if it.kind in ("part", "chapter"):
            flush_chapter()
            n += 1
            tag = "h1" if it.kind == "part" else "h2"
            body.append(f'<{tag} id="c{n}" class="{it.kind}">{html.escape(it.text)}</{tag}>')
            toc.append(f'<li class="{it.kind}"><a href="#c{n}">{html.escape(it.text)}</a></li>')
        elif it.kind == "scene_break":
            pending_blocks.append(Item("block", node={"type": "_break"}))
        elif it.kind == "notes":
            notes_buffer.extend(it.notes)
            flush_chapter()
        else:
            pending_blocks.append(it)
    flush_chapter()

    font = (FONT_DIR / "NotoNaskhArabic-Regular.ttf").as_uri()
    font_b = (FONT_DIR / "NotoNaskhArabic-Bold.ttf").as_uri()
    css = f"""
    @font-face {{ font-family: "Noto Naskh Arabic"; src: url("{font}"); }}
    @font-face {{ font-family: "Noto Naskh Arabic"; font-weight: bold; src: url("{font_b}"); }}
    @page {{ size: A5; margin: 20mm 18mm 22mm;
             @bottom-center {{ content: counter(page, arabic-indic); font: 9pt "Noto Naskh Arabic"; }} }}
    @page :first {{ @bottom-center {{ content: none; }} }}
    @page toc {{ @bottom-center {{ content: none; }} }}
    html {{ direction: {'rtl' if rtl else 'ltr'}; font-family: "Noto Naskh Arabic", serif; font-size: 11.5pt; line-height: 1.95; }}
    .title {{ page: first; text-align: center; padding-top: 55mm; page-break-after: always; }}
    .title h1 {{ font-size: 24pt; margin: 0; }} .title p {{ margin: 6mm 0 0; }}
    nav {{ page: toc; page-break-after: always; }} nav h1 {{ text-align: center; font-size: 16pt; }}
    .title h1, nav h1 {{ bookmark-level: none; }}
    h1.part {{ bookmark-level: 1; }} h2.chapter {{ bookmark-level: 2; }}
    nav ol {{ list-style: none; padding: 0; margin: 0; }}
    nav li a {{ color: inherit; text-decoration: none; }}
    nav li a::after {{ content: leader(".") target-counter(attr(href), page, arabic-indic); }}
    nav li.chapter {{ padding-inline-start: 6mm; }}
    h1.part {{ page-break-before: always; text-align: center; font-size: 20pt; margin-top: 40mm; }}
    h2.chapter {{ page-break-before: always; text-align: center; font-size: 16pt; margin: 18mm 0 10mm; }}
    h1.part + h2.chapter {{ page-break-before: avoid; }}
    p {{ text-align: justify; text-indent: 1.2em; margin: 0 0 .35em; orphans: 2; widows: 2; }}
    h3 {{ text-align: center; font-size: 13.5pt; }}
    blockquote {{ margin: .6em 10mm; }}
    .break {{ text-align: center; text-indent: 0; margin: .8em 0; }}
    .fn {{ float: footnote; font-size: 9.5pt; line-height: 1.6; text-align: start; text-indent: 0; }}
    ::footnote-call {{ content: counter(footnote, arabic-indic); font-size: 70%; vertical-align: super; }}
    ::footnote-marker {{ content: "(" counter(footnote, arabic-indic) ") "; }}
    @page {{ @footnote {{ border-top: .4pt solid #999; padding-top: 2mm; }} }}
    """
    title = (f'<section class="title"><h1>{html.escape(book.title)}</h1>'
             + (f"<p>{html.escape(book.subtitle)}</p>" if book.subtitle else "")
             + (f"<p>{html.escape(book.author)}</p>" if book.author else "") + "</section>")
    nav = f'<nav><h1>المحتويات</h1><ol>{"".join(toc)}</ol></nav>' if toc else ""
    return (f'<!doctype html><html lang="{book.language}" dir="{"rtl" if rtl else "ltr"}"><head><meta charset="utf-8">'
            f"<title>{html.escape(book.title)}</title><meta name=author content=\"{html.escape(book.author)}\"><meta name=generator content=\"كاتب\">"
            f"<style>{css}</style></head><body>{title}{nav}{''.join(body)}</body></html>")


def _render_block(b: dict) -> str:
    t = b.get("type")
    if t == "_break":
        return f'<p class="break">{SCENE_BREAK}</p>'
    inner = _inline(b)
    if t == "heading":
        return f"<h3>{inner}</h3>"
    if t == "blockquote":
        return f"<blockquote><p>{inner}</p></blockquote>"
    if t == "horizontalRule":
        return "<hr>"
    return f"<p>{inner}</p>"


def to_pdf_html(book: Book) -> bytes:
    from weasyprint import HTML

    return HTML(string=book_html(book), base_url=str(FONT_DIR)).write_pdf(pdf_variant="pdf/ua-1")
