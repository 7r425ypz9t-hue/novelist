"""Phase 1 vertical slice: project → chapter → scene → write → autosave → revisions → restore (AT01–AT05)."""

import pytest
from sqlalchemy import select

from nis.db import SessionLocal
from nis.models import Revision


def _slice(w):
    p = w.project("بحر الشمال", word_goal=1000)
    ch = w.node(p["id"], "chapter", "الفصل الأول")
    sc = w.node(p["id"], "scene", "المشهد الأول", parent=ch["id"])
    return p, ch, sc


def test_AT01_records_persist_across_sessions(client, writer):
    p, ch, sc = _slice(writer)
    r = writer.write(sc["document_id"], "كتب نادر أول سطر في دفتره.")
    assert r.status_code == 200, r.text
    # new session (login again) sees everything
    tok = client.post("/v1/auth/login", json={"email": writer.email, "password": "correct-horse-1"}).json()["token"]
    tree = client.get(f"/v1/projects/{p['id']}/tree", headers={"Authorization": f"Bearer {tok}"}).json()
    nodes = tree["manuscripts"][0]["nodes"]
    assert [n["type"] for n in nodes] == ["chapter", "scene"]
    assert nodes[1]["label"] == "الفصل 1 · المشهد 1"
    doc = client.get(f"/v1/documents/{sc['document_id']}", headers={"Authorization": f"Bearer {tok}"}).json()
    assert doc["word_count"] == 6


def test_AT02_mixed_direction_content_roundtrips(writer):
    _, _, sc = _slice(writer)
    content = {"type": "doc", "content": [
        {"type": "paragraph", "attrs": {"dir": "rtl"}, "content": [
            {"type": "text", "text": "قال: «سأصل في 10:30 مع John إلى Port-Said» ثم مضى، أليس كذلك؟"}]},
        {"type": "paragraph", "attrs": {"dir": "ltr"}, "content": [{"type": "text", "text": "An English note."}]},
    ]}
    v = writer.get(f"/v1/documents/{sc['document_id']}").json()["version"]
    r = writer.put(f"/v1/documents/{sc['document_id']}", headers={"If-Match": f'W/"{v}"'},
                   json={"content_json": content, "kind": "checkpoint"})
    assert r.status_code == 200
    back = writer.get(f"/v1/documents/{sc['document_id']}").json()["content_json"]
    assert back == content  # quotes, digits, Latin runs and per-paragraph direction preserved exactly


def test_AT03_offline_replay_is_idempotent(writer):
    _, _, sc = _slice(writer)
    d = sc["document_id"]
    r1 = writer.write(d, "مسودة كُتبت دون اتصال", kind="autosave", save_id="client-save-0001")
    v_after = r1.json()["version"]
    # the browser reconnects and replays the queued save with the *old* version: same id → same revision
    r2 = writer.write(d, "مسودة كُتبت دون اتصال", kind="autosave", version=v_after - 1, save_id="client-save-0001")
    assert r2.status_code == 200 and r2.json()["created"] is False
    assert r2.json()["revision"]["id"] == r1.json()["revision"]["id"]


def test_AT04_stale_write_is_refused_not_overwritten(make_writer):
    owner, editor = make_writer("owner"), make_writer("editor")
    p, _, sc = _slice(owner)
    owner.post(f"/v1/projects/{p['id']}/members", json={"email": editor.email, "role": "editor"})
    d = sc["document_id"]
    base = owner.get(f"/v1/documents/{d}").json()["version"]
    assert owner.write(d, "نسخة المالك", version=base).status_code == 200
    r = editor.write(d, "نسخة المحرر على أساس قديم", version=base)
    assert r.status_code == 412
    assert r.json()["type"] == "/problems/version-conflict"
    assert owner.get(f"/v1/documents/{d}").json()["content_json"]["content"][0]["content"][0]["text"] == "نسخة المالك"
    # and a write without If-Match is rejected outright
    assert editor.put(f"/v1/documents/{d}", json={"content_json": {"type": "doc"}}).status_code == 428


def test_AT05_restore_creates_new_revision_and_keeps_history(writer):
    _, _, sc = _slice(writer)
    d = sc["document_id"]
    writer.write(d, "النص الأول")
    writer.write(d, "النص الثاني")
    revs = writer.get(f"/v1/documents/{d}/revisions").json()["items"]
    first = next(r for r in revs if r["word_count"] == 2 and r["revision_no"] == 2)
    v = writer.get(f"/v1/documents/{d}").json()["version"]
    r = writer.post(f"/v1/revisions/{first['id']}/restore", headers={"If-Match": f'W/"{v}"'})
    assert r.status_code == 200
    after = writer.get(f"/v1/documents/{d}/revisions").json()["items"]
    assert len(after) == len(revs) + 1
    assert after[0]["kind"] == "restore" and after[0]["label"].startswith("استعادة")
    diff = writer.get(f"/v1/documents/{d}/diff", params={"a": after[1]["id"], "b": after[0]["id"]}).json()
    assert diff["stats"]["deleted_words"] >= 1


def test_revisions_are_immutable_at_orm_level(writer):
    _, _, sc = _slice(writer)
    writer.write(sc["document_id"], "نص")
    db = SessionLocal()
    try:
        rev = db.scalars(select(Revision)).first()
        rev.label = "تلاعب"
        with pytest.raises(RuntimeError):
            db.flush()
    finally:
        db.rollback()
        db.close()


def test_reorder_keeps_ids_and_trash_restore(writer):
    p = writer.project()
    a = writer.node(p["id"], "chapter", "أ")
    b = writer.node(p["id"], "chapter", "ب")
    s = writer.node(p["id"], "scene", "مشهد", parent=a["id"])
    assert writer.patch(f"/v1/nodes/{s['id']}/reorder", json={"parent_id": b["id"], "position": 0}).status_code == 200
    nodes = writer.get(f"/v1/projects/{p['id']}/tree").json()["manuscripts"][0]["nodes"]
    moved = next(n for n in nodes if n["id"] == s["id"])
    assert moved["parent_id"] == b["id"]
    assert writer.patch(f"/v1/nodes/{s['id']}/reorder", json={"parent_id": None, "position": 0}).status_code == 400
    assert writer.delete(f"/v1/nodes/{b['id']}").json() == {"trashed": 2}
    assert len(writer.get(f"/v1/projects/{p['id']}/tree").json()["manuscripts"][0]["nodes"]) == 1
    assert writer.post(f"/v1/nodes/{b['id']}/restore").status_code == 200
    assert len(writer.get(f"/v1/projects/{p['id']}/tree").json()["manuscripts"][0]["nodes"]) == 3


def test_import_preview_and_commit(writer):
    p = writer.project()
    md = "# الفصل الأول\n\nكان الليل طويلاً.\n\n# الفصل الثاني\n\nثم جاء الصباح.".encode()
    prev = writer.post(f"/v1/projects/{p['id']}/import/preview", files={"file": ("novel.md", md, "text/markdown")})
    assert prev.status_code == 200, prev.text
    chapters = prev.json()["chapters"]
    assert [c["title"] for c in chapters] == ["الفصل الأول", "الفصل الثاني"]
    r = writer.post(f"/v1/projects/{p['id']}/import/commit", json={"chapters": chapters})
    assert r.status_code == 201 and len(r.json()["created"]) == 2
    dash = writer.get(f"/v1/projects/{p['id']}/dashboard").json()
    assert dash["counts"]["chapters"] == 2 and dash["words"] == 6


def test_manuscript_search_is_arabic_aware_ordered_and_member_only(writer, other):
    p, ch, sc = _slice(writer)
    sc2 = writer.node(p["id"], "scene", "المشهد الثاني", parent=ch["id"])
    assert writer.write(sc["document_id"], "وصلت السفينةُ إلى الميناء.\n\nثم غادرت السفينه فجراً.").status_code == 200
    assert writer.write(sc2["document_id"], "لم يبقَ في المرفأ إلا سفينة واحدة.").status_code == 200
    r = writer.get(f"/v1/projects/{p['id']}/manuscript/search", params={"q": "السفينة"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 2 and body["units"] == 1                      # «سفينة» alone is not «السفينة»
    hit = body["items"][0]
    assert hit["node_id"] == sc["id"] and hit["label"].endswith("المشهد 1")
    assert [s["match"] for s in hit["snippets"]] == ["السفينةُ", "السفينه"]
    assert writer.get(f"/v1/projects/{p['id']}/manuscript/search", params={"q": "سفينة"}).json()["total"] == 3
    assert writer.get(f"/v1/projects/{p['id']}/manuscript/search",
                      params={"q": "سفينة", "whole_word": True}).json()["total"] == 3   # «ال» is a proclitic
    assert writer.get(f"/v1/projects/{p['id']}/manuscript/search",
                      params={"q": "سفينة", "whole_word": True, "clitics": False}).json()["total"] == 1
    sn = hit["snippets"][0]
    assert sn["before"] == "وصلت " and sn["cut_before"] is False and sn["after"].startswith(" إلى")
    assert other.get(f"/v1/projects/{p['id']}/manuscript/search", params={"q": "سفينة"}).status_code == 404
    assert writer.get(f"/v1/projects/{p['id']}/manuscript/search", params={"q": "x" * 201}).status_code == 422
