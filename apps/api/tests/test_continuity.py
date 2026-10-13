"""Continuity with evidence (AT08, AT09, AT22, scenario B)."""

from nis.services.continuity import parse_age


def test_parse_age_words_and_digits():
    assert parse_age("12") == 12
    assert parse_age("الخامسه والعشرين") == 25
    assert parse_age("ثلاثين") == 30


def _novel(w):
    p = w.project("ذاكرة الميناء")
    hero = w.post(f"/v1/projects/{p['id']}/characters",
                   json={"canonical_name": "نادر", "profile": {"birth_year": 1945}}).json()
    ch1 = w.node(p["id"], "chapter", "الطفولة", meta={"story_time": 1957})
    w.write(ch1["document_id"], "كان نادر في الثانية عشرة من عمره حين غرق القارب.")
    ch3 = w.node(p["id"], "chapter", "العودة", meta={"story_time": 1972})
    return p, hero, ch1, ch3


def test_scenario_B_age_change_in_chapter_is_reported_with_both_spans(writer):
    p, hero, ch1, ch3 = _novel(writer)
    writer.write(ch3["document_id"], "عاد نادر وهو في الثلاثين من عمره إلى الميناء.")
    stats = writer.post(f"/v1/projects/{p['id']}/continuity/scan").json()
    assert stats["created"] >= 2
    items = writer.get(f"/v1/projects/{p['id']}/conflicts").json()["items"]
    pair = next(c for c in items if c["rule"] == "R-AGE-PAIR")
    assert pair["severity"] == "high"
    labels = [e["label"] for e in pair["evidence"]]
    assert labels == ["الفصل 1 — الطفولة", "الفصل 2 — العودة"]
    assert "الثانية عشرة" in pair["evidence"][0]["quote"] and "الثلاثين" in pair["evidence"][1]["quote"]
    assert pair["evidence"][1]["document_id"] == ch3["document_id"]
    # fixing the text auto-resolves the conflict on the next scan
    writer.write(ch3["document_id"], "عاد نادر وهو في السابعة والعشرين من عمره إلى الميناء.")
    writer.post(f"/v1/projects/{p['id']}/continuity/scan")
    assert not [c for c in writer.get(f"/v1/projects/{p['id']}/conflicts").json()["items"] if c["rule"].startswith("R-AGE")]


def test_AT08_moving_event_date_creates_conflict_with_evidence(writer):
    p, hero, ch1, ch3 = _novel(writer)
    ev = writer.post(f"/v1/projects/{p['id']}/events",
                     json={"title": "رحلة البصرة", "story_time_start": 1960, "participant_ids": [hero["id"]],
                           "node_id": ch3["id"]}).json()
    writer.post(f"/v1/projects/{p['id']}/continuity/scan")
    before = {c["rule"] for c in writer.get(f"/v1/projects/{p['id']}/conflicts").json()["items"]}
    assert "R-EVENT-BIRTH" not in before
    writer.patch(f"/v1/projects/{p['id']}/events/{ev['id']}", json={"story_time_start": 1940})
    writer.post(f"/v1/projects/{p['id']}/continuity/scan")
    items = writer.get(f"/v1/projects/{p['id']}/conflicts").json()["items"]
    c = next(c for c in items if c["rule"] == "R-EVENT-BIRTH")
    kinds = {(e.get("entity_type"), e.get("field")) for e in c["evidence"]}
    assert ("event", "story_time_start") in kinds and ("character", "birth_year") in kinds
    assert any(e.get("entity_type") == "node" for e in c["evidence"])  # the narrative scope (linked chapter)
    assert any(x["rule"] == "R-EVENT-SCENE" for x in items)  # chapter time 1972 vs event 1940


def test_AT09_waiver_for_unreliable_narrator_persists(writer):
    p, hero, ch1, ch3 = _novel(writer)
    writer.write(ch3["document_id"], "قال نادر إنه في العشرين من عمره، وكان يكذب كعادته.")
    writer.post(f"/v1/projects/{p['id']}/continuity/scan")
    c = next(c for c in writer.get(f"/v1/projects/{p['id']}/conflicts").json()["items"] if c["rule"] == "R-AGE-PAIR")
    assert writer.post(f"/v1/projects/{p['id']}/conflicts/{c['id']}/resolve",
                       json={"action": "waive", "note": ""}).status_code == 400
    r = writer.post(f"/v1/projects/{p['id']}/conflicts/{c['id']}/resolve",
                    json={"action": "waive", "note": "راوٍ غير موثوق: نادر يكذب في عمره عمداً"})
    assert r.json()["state"] == "waived"
    writer.post(f"/v1/projects/{p['id']}/continuity/scan")
    waived = writer.get(f"/v1/projects/{p['id']}/conflicts", params={"state": "waived"}).json()["items"]
    assert [x["id"] for x in waived] == [c["id"]]
    facts = writer.get(f"/v1/projects/{p['id']}/facts").json()["items"]
    assert facts == []  # the waiver did not change any fact


def test_AT22_two_sources_disagree_no_forced_decision(writer):
    p = writer.project()
    for v, src in ((1932, "مصدر أ"), (1934, "مصدر ب")):
        writer.post(f"/v1/projects/{p['id']}/facts", json={
            "subject_label": "تأسيس المدرسة", "predicate": "سنة التأسيس", "object": {"value": v},
            "epistemic_status": "external", "source_refs": [{"title": src}]})
    writer.post(f"/v1/projects/{p['id']}/continuity/scan")
    c = next(c for c in writer.get(f"/v1/projects/{p['id']}/conflicts").json()["items"] if c["rule"] == "R-FACT")
    assert c["severity"] == "low" and "لا يحسم" in c["explanation"]
    assert {e["value"] for e in c["evidence"]} == {1932, 1934}
    assert {e["source_refs"][0]["title"] for e in c["evidence"]} == {"مصدر أ", "مصدر ب"}


def test_canon_requires_author_approval(make_writer):
    owner, editor = make_writer("o"), make_writer("e")
    p = owner.project()
    owner.post(f"/v1/projects/{p['id']}/members", json={"email": editor.email, "role": "editor"})
    f = editor.post(f"/v1/projects/{p['id']}/facts", json={"predicate": "لون البيت", "object": {"value": "أزرق"}}).json()
    assert f["epistemic_status"] == "draft"
    assert editor.post(f"/v1/projects/{p['id']}/facts", json={"predicate": "x", "epistemic_status": "canon"}).status_code == 422
    assert editor.post(f"/v1/projects/{p['id']}/facts/{f['id']}/approve").status_code == 403
    r = owner.post(f"/v1/projects/{p['id']}/facts/{f['id']}/approve").json()
    assert r["epistemic_status"] == "canon" and r["approved_by"] == owner.user["id"]
