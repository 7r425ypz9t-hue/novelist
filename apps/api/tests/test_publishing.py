"""Exports open in independent readers (AT16), data export (AT21), backup → restore (AT17), deletion."""

import io
import zipfile
from xml.dom import minidom

import pytest


@pytest.fixture
def book(writer):
    p = writer.project("ملح الضفة", author_name="مؤلف الاختبار")
    ms = p["manuscript_id"]
    writer.patch(f"/v1/manuscripts/{ms}", json={"author_name": "مؤلف الاختبار"})
    part = writer.node(p["id"], "part", "الجزء الأول")
    ch1 = writer.node(p["id"], "chapter", "البحر", parent=part["id"])
    s1 = writer.node(p["id"], "scene", "", parent=ch1["id"])
    s2 = writer.node(p["id"], "scene", "", parent=ch1["id"])
    ch2 = writer.node(p["id"], "chapter", "العودة", parent=part["id"])
    content = {"type": "doc", "content": [
        {"type": "paragraph", "content": [
            {"type": "text", "text": "قال سالم: «سأعود في عام 1972 مع "},
            {"type": "text", "text": "John", "marks": [{"type": "italic"}]},
            {"type": "text", "text": "» ثم مضى", "marks": [{"type": "footnote", "attrs": {"note": "حاشية تجريبية"}}]}]},
        {"type": "blockquote", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "البحر لا يعيد ما يأخذه."}]}]},
    ]}
    for node in (s1, s2, ch2):
        v = writer.get(f"/v1/documents/{node['document_id']}").json()["version"]
        writer.put(f"/v1/documents/{node['document_id']}", headers={"If-Match": f'W/"{v}"'},
                   json={"content_json": content, "kind": "checkpoint"})
    return writer, p


def _download(w, pid, fmt):
    e = w.post(f"/v1/projects/{pid}/exports", json={"format": fmt})
    assert e.status_code == 201, e.text
    r = w.get(f"/v1/exports/{e.json()['id']}/download")
    assert r.status_code == 200
    assert e.json()["sha256"] == r.headers["x-content-sha256"]
    return r.content


def test_AT16_docx_is_rtl_with_toc_and_chapters(book):
    import docx

    w, p = book
    data = _download(w, p["id"], "docx")
    d = docx.Document(io.BytesIO(data))
    texts = [x.text for x in d.paragraphs]
    assert "البحر" in texts and "العودة" in texts and "الجزء الأول" in texts and "المحتويات" in texts
    xml = d.element.xml
    assert "<w:bidi/>" in xml and "<w:rtl/>" in xml and 'TOC \\o "1-2"' in xml
    assert "Noto Naskh Arabic" in xml
    assert "حاشية تجريبية" in "\n".join(texts)
    assert texts.count("⁂") == 1  # one scene break between the two scenes of chapter 1


def test_AT16_epub_is_valid_rtl_package(book):
    w, p = book
    data = _download(w, p["id"], "epub")
    z = zipfile.ZipFile(io.BytesIO(data))
    first = z.infolist()[0]
    assert first.filename == "mimetype" and first.compress_type == zipfile.ZIP_STORED
    assert z.read("mimetype") == b"application/epub+zip"
    for name in z.namelist():
        if name.endswith((".xhtml", ".opf", ".ncx", ".xml")):
            minidom.parseString(z.read(name))  # well-formed XML
    opf = z.read("OEBPS/content.opf").decode()
    assert 'page-progression-direction="rtl"' in opf and "<dc:language>ar</dc:language>" in opf
    nav = z.read("OEBPS/nav.xhtml").decode()
    assert "البحر" in nav and "العودة" in nav
    chap = next(z.read(n).decode() for n in z.namelist() if n.startswith("OEBPS/chap") and "البحر" in z.read(n).decode())
    assert 'dir="rtl"' in chap and 'epub:type="footnote"' in chap and "<em>John</em>" in chap


def test_AT16_pdf_opens_with_outline_and_arabic_font(book):
    from pypdf import PdfReader

    w, p = book
    data = _download(w, p["id"], "pdf")
    assert data.startswith(b"%PDF")
    r = PdfReader(io.BytesIO(data))
    assert len(r.pages) >= 4  # title + toc + content
    titles = [o.title if hasattr(o, "title") else None for o in _flatten(r.outline)]
    assert "البحر" in titles and "العودة" in titles
    fonts = [f.get_object()["/BaseFont"] for f in r.pages[2]["/Resources"]["/Font"].values()]
    assert any("NotoNaskhArabic" in f for f in fonts)  # embedded licensed Arabic font (OFL)


def _flatten(items):
    for i in items:
        if isinstance(i, list):
            yield from _flatten(i)
        else:
            yield i


def test_markdown_export(book):
    w, p = book
    md = _download(w, p["id"], "md").decode()
    assert md.startswith("# ملح الضفة") and "## البحر" in md and "[^1]: حاشية تجريبية" in md


def test_AT21_AT17_data_export_then_verified_restore(book):
    w, p = book
    w.post(f"/v1/projects/{p['id']}/characters", json={"canonical_name": "سالم", "aliases": ["أبو البحر"]})
    w.post(f"/v1/projects/{p['id']}/sources", data={"license_state": "owned", "usage_consent": "true"},
           files={"file": ("notes.txt", "افتتح الميناء عام 1958".encode(), "text/plain")})
    r = w.post(f"/v1/projects/{p['id']}/data-export")
    assert r.status_code == 200
    z = zipfile.ZipFile(io.BytesIO(r.content))
    names = set(z.namelist())
    assert {"manifest.json", "project.json", "manuscript.md", "README.txt"} <= names
    assert any(n.startswith("sources/") for n in names)

    restored = w.post("/v1/projects/import", files={"file": ("a.zip", r.content, "application/zip")})
    assert restored.status_code == 201, restored.text
    np = restored.json()["id"]
    assert np != p["id"]
    t_old = w.get(f"/v1/projects/{p['id']}/tree").json()["manuscripts"][0]["nodes"]
    t_new = w.get(f"/v1/projects/{np}/tree").json()["manuscripts"][0]["nodes"]
    assert [(n["type"], n["title"], n["word_count"]) for n in t_old] == [(n["type"], n["title"], n["word_count"]) for n in t_new]
    old_doc = next(n for n in t_old if n["type"] == "scene")["document_id"]
    new_doc = next(n for n in t_new if n["type"] == "scene")["document_id"]
    assert len(w.get(f"/v1/documents/{old_doc}/revisions").json()["items"]) == \
        len(w.get(f"/v1/documents/{new_doc}/revisions").json()["items"])
    assert w.get(f"/v1/documents/{new_doc}").json()["content_json"] == w.get(f"/v1/documents/{old_doc}").json()["content_json"]
    assert w.get(f"/v1/projects/{np}/characters").json()["items"][0]["aliases"] == ["أبو البحر"]
    q = w.post(f"/v1/projects/{np}/research/query", json={"question": "افتتح الميناء 1958"}).json()
    assert q["verdict"] == "evidence_found"
    # the restored copy is fully writable with a fresh version chain
    assert w.write(new_doc, "تعديل بعد الاسترجاع").status_code == 200

    # tampering is detected
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as out:
        for n in z.namelist():
            data = z.read(n)
            if n == "manuscript.md":
                data += b"\ntampered"
            out.writestr(n, data)
    bad = w.post("/v1/projects/import", files={"file": ("b.zip", buf.getvalue(), "application/zip")})
    assert bad.status_code == 400 and "سلامة" in bad.json()["detail"]


def test_project_deletion_requires_typed_title(book, other):
    w, p = book
    assert other.delete(f"/v1/projects/{p['id']}", json={"confirm_title": p["title"]}).status_code == 404
    assert w.delete(f"/v1/projects/{p['id']}", json={"confirm_title": "خطأ"}).status_code == 400
    r = w.delete(f"/v1/projects/{p['id']}", json={"confirm_title": p["title"]})
    assert r.status_code == 200 and "النسخ الاحتياطية" in r.json()["retention"]
    assert w.get(f"/v1/projects/{p['id']}").status_code == 404
