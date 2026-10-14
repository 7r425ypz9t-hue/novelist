"""Two computers, one novel: an archive moved to another computer keeps the novel's identity, and an archive from
that computer updates the project here without overwriting anything (fast-forward, keep local, or diverged)."""

import io

import pytest


def _zip(w, pid):
    r = w.post(f"/v1/projects/{pid}/data-export")
    assert r.status_code == 200
    return r.content


def _move_here(w, archive, pid, title):
    """Simulate «the other computer»: the project disappears from this server and arrives from an archive."""
    if w.get(f"/v1/projects/{pid}").status_code == 200:
        assert w.delete(f"/v1/projects/{pid}", json={"confirm_title": title}).status_code in (200, 204)
    r = w.post("/v1/projects/import", files={"file": ("a.zip", archive, "application/zip")})
    assert r.status_code == 201, r.text
    assert r.json()["id"] == pid and r.json()["title"] == title          # same novel, same identity
    return r.json()


def _merge(w, pid, archive):
    return w.post(f"/v1/projects/{pid}/data-merge", files={"file": ("b.zip", archive, "application/zip")})


def _text(w, doc):
    return w.get(f"/v1/documents/{doc}").json()


@pytest.fixture
def novel(writer):
    p = writer.project("رواية الجهازين")
    ch = writer.node(p["id"], "chapter", "الأول")
    assert writer.write(ch["document_id"], "السطر الأول.").status_code == 200
    return writer, p["id"], ch["document_id"], "رواية الجهازين"


def test_fast_forward_new_units_and_bible_from_the_other_computer(novel):
    w, pid, doc, title = novel
    at_r1 = _zip(w, pid)                                   # the laptop's last sync point
    w.write(doc, "السطر الأول.\n\nوسطر ثانٍ كُتب على المكتب.")
    ch2 = w.node(pid, "chapter", "الثاني")
    w.write(ch2["document_id"], "فصل جديد.")
    w.post(f"/v1/projects/{pid}/characters", json={"canonical_name": "مريم"})
    office = _zip(w, pid)

    _move_here(w, at_r1, pid, title)                       # now we are the laptop, still at r1
    assert "وسطر ثانٍ" not in str(_text(w, doc)["content_json"])
    before = len(w.get(f"/v1/documents/{doc}/revisions").json()["items"])
    rep = _merge(w, pid, office)
    assert rep.status_code == 200, rep.text
    rep = rep.json()
    assert [d["title"] for d in rep["documents"]["fast_forward"]] == ["الأول"]
    assert [d["title"] for d in rep["documents"]["new"]] == ["الثاني"] and not rep["documents"]["diverged"]
    assert rep["added"]["characters"] == 1 and rep["added"]["nodes"] == 1
    assert "وسطر ثانٍ" in str(_text(w, doc)["content_json"])
    assert len(w.get(f"/v1/documents/{doc}/revisions").json()["items"]) == before + 1   # the office revision
    # merging the same archive again changes nothing (idempotent)
    again = _merge(w, pid, office).json()
    assert not again["added"] and not any(again["documents"].values())
    # the laptop keeps writing normally afterwards
    assert w.write(doc, "بعد الدمج.").status_code == 200


def test_local_newer_stays_and_divergence_never_overwrites(novel):
    w, pid, doc, title = novel
    base = _zip(w, pid)
    w.write(doc, "نسخة المكتب.")
    office = _zip(w, pid)

    _move_here(w, base, pid, title)
    w.write(doc, "نسخة المحمول.")                          # both changed the same unit independently
    laptop = _zip(w, pid)

    rep = _merge(w, pid, office).json()
    assert [d["title"] for d in rep["documents"]["diverged"]] == ["الأول"]
    assert "نسخة المحمول" in str(_text(w, doc)["content_json"])  # the text here is untouched
    revs = w.get(f"/v1/documents/{doc}/revisions").json()["items"]
    foreign = [r for r in revs if "من جهاز آخر" in (r.get("label") or "")]
    assert len(foreign) == 1 and len({r["revision_no"] for r in revs}) == len(revs)   # renumbered, no clash
    # the author can bring the other version in with the normal restore (a new revision, history kept)
    v = _text(w, doc)["version"]
    r = w.post(f"/v1/revisions/{foreign[0]['id']}/restore", headers={"If-Match": f'W/"{v}"'})
    assert r.status_code in (200, 201), r.text
    assert "نسخة المكتب" in str(_text(w, doc)["content_json"])

    # an older archive of this same project: local is ahead, nothing moves back
    rep = _merge(w, pid, laptop).json()
    assert not rep["documents"]["fast_forward"] and "نسخة المكتب" in str(_text(w, doc)["content_json"])


def test_merge_is_owner_only_and_refuses_another_novel(novel, make_writer):
    w, pid, doc, title = novel
    other = w.project("رواية أخرى")
    foreign = _zip(w, other["id"])
    r = _merge(w, pid, foreign)
    assert r.status_code == 409 and r.json()["type"] == "/problems/archive-other-project"
    stranger = make_writer("stranger")
    assert _merge(stranger, pid, _zip(w, pid)).status_code == 404
    bad = io.BytesIO(b"not a zip").getvalue()
    assert _merge(w, pid, bad).status_code == 400
