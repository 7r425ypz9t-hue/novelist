"""Agents produce proposals only; humans decide (AT06, AT07, AT14, AT19, AT20)."""

import pytest

from nis.config import get_settings

TEXT = """قال سالم وهو ينظر إلى البحر: «لن أعود?» ثم صمت طويلاً, وكان الموج يضرب الصخور.

قال سالم وهو ينظر إلى البحر: «لن أعود?» ثم صمت طويلاً, وكان الموج يضرب الصخور.

كان يمشي في في الطريق إلى البيت .. ولا يلتفت."""


@pytest.fixture
def novel(writer):
    p = writer.project("موج")
    ch = writer.node(p["id"], "chapter", "البحر")
    writer.write(ch["document_id"], TEXT)
    return writer, p, ch


def _props(w, pid, **params):
    return w.get(f"/v1/projects/{pid}/proposals", params={"state": "pending", **params}).json()["items"]


def test_AT06_deletion_is_only_a_proposal_until_author_confirms(novel):
    w, p, ch = novel
    run = w.run(p["id"], "A10").json()
    assert run["status"] == "succeeded", run
    before = w.get(f"/v1/documents/{ch['document_id']}").json()
    dup = next(x for x in _props(w, p["id"]) if x["patch"]["ops"][0]["op"] == "delete_block")
    assert dup["ai_generated"] and dup["risk_level"] == "MEDIUM" and dup["evidence_refs"]
    assert w.get(f"/v1/documents/{ch['document_id']}").json()["version"] == before["version"]  # untouched
    preview = w.get(f"/v1/proposals/{dup['id']}").json()["preview"]
    assert preview["applicable"] and any(s["op"] == "delete" for s in preview["diff"])
    r = w.post(f"/v1/proposals/{dup['id']}/accept", json={})
    assert r.status_code == 200
    after = w.get(f"/v1/documents/{ch['document_id']}").json()
    assert after["version"] == before["version"] + 1
    assert after["content_json"]["content"].__len__() == 2
    rev = w.get(f"/v1/documents/{ch['document_id']}/revisions").json()["items"][0]
    assert rev["author_type"] == "human_accepted_ai" and rev["source_proposal_id"] == dup["id"]


def test_AT07_rejection_changes_nothing(novel):
    w, p, ch = novel
    w.run(p["id"], "A11")
    before = w.get(f"/v1/documents/{ch['document_id']}").json()
    facts_before = w.get(f"/v1/projects/{p['id']}/facts").json()["items"]
    for x in _props(w, p["id"]):
        assert w.post(f"/v1/proposals/{x['id']}/reject", json={"note": "أفضّل الصيغة الأصلية"}).status_code == 200
    assert w.get(f"/v1/documents/{ch['document_id']}").json() == before
    assert w.get(f"/v1/projects/{p['id']}/facts").json()["items"] == facts_before
    assert _props(w, p["id"]) == []


def test_AT20_retries_never_duplicate_proposals(novel):
    w, p, ch = novel
    r1 = w.run(p["id"], "A11", key="retry-key-0001").json()
    r2 = w.run(p["id"], "A11", key="retry-key-0001").json()
    assert r2["id"] == r1["id"] and r2["deduplicated"] is True
    n = len(_props(w, p["id"]))
    w.run(p["id"], "A11", key="retry-key-0002")  # a genuine re-run on the same base revision
    assert len(_props(w, p["id"])) == n


def test_lint_patches_apply_cleanly_and_modify_is_supported(novel):
    w, p, ch = novel
    w.run(p["id"], "A11")
    props = _props(w, p["id"])
    comma = next(x for x in props if "الفاصلة العربية" in x["title"])
    edited = [{**op, "text": "،  "} for op in comma["patch"]["ops"]]
    r = w.post(f"/v1/proposals/{comma['id']}/accept", json={"edited_ops": edited, "note": "تعديل يدوي"})
    assert r.status_code == 200 and r.json()["result"]["modified"] is True
    # other proposals were made against the previous revision → stale unless the author opts to rebase
    q = next(x for x in _props(w, p["id"]) if "الاستفهام" in x["title"])
    stale = w.post(f"/v1/proposals/{q['id']}/accept", json={})
    assert stale.status_code == 409 and stale.json()["type"] == "/problems/stale-proposal"
    ok = w.post(f"/v1/proposals/{q['id']}/accept", json={"allow_rebase": True})
    assert ok.status_code == 200
    block = w.get(f"/v1/documents/{ch['document_id']}").json()["content_json"]["content"][0]
    assert len(block["content"]) == 1  # adjacent text nodes are merged after patching
    text = block["content"][0]["text"]
    assert "؟" in text and "?" not in text and "،" in text


def test_AT14_without_provider_writing_and_analysis_still_work(novel):
    w, p, ch = novel
    cat = w.get("/v1/agents/catalog").json()
    assert cat["provider"]["available"] is False and "حتمي" in cat["provider"]["destination"]
    run = w.run(p["id"], "A00", use_model=True).json()  # asks for a model, none configured
    assert run["status"] == "succeeded" and run["provider"] == "disabled"
    report = run["output"]["report"]
    assert report["sections"] and "لم يُعدَّل أي نص" in report["disclaimer"]
    sk12 = run["output"]["results"]["A06:SK12"]
    assert any("يتطلب مزوداً" in x for x in sk12["warnings"])
    assert w.write(ch["document_id"], "ما زالت الكتابة اليدوية تعمل.").status_code == 200


def test_AT19_critique_findings_carry_certainty_and_evidence(novel):
    w, p, ch = novel
    run = w.run(p["id"], "A00").json()
    findings = [f for res in run["output"]["results"].values() for f in res["findings"]]
    assert findings
    assert all(f["certainty"] in ("supported", "inferred", "speculative") for f in findings)
    assert all(f["kind"] in ("objective", "taste") for f in findings)
    sections = run["output"]["report"]["sections"]
    assert all(set(v) == {"objective", "taste"} for v in sections.values())


def test_external_provider_is_consent_gated(novel, monkeypatch):
    w, p, ch = novel
    monkeypatch.setenv("NIS_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("NIS_LLM_API_KEY", "test-key-not-used")
    get_settings.cache_clear()
    try:
        r = w.run(p["id"], "A10", use_model=True)
        assert r.status_code == 403 and r.json()["type"] == "/problems/consent-required"
        dest = r.json()["destination"]
        assert "anthropic" in dest
        assert w.post(f"/v1/projects/{p['id']}/consents",
                      json={"kind": "external_ai", "acknowledge_destination": dest}).status_code == 201
        r = w.run(p["id"], "A10", use_model=True)
        assert r.status_code == 428 and r.json()["type"] == "/problems/acknowledge-external"
        r = w.run(p["id"], "A10", use_model=True, acknowledge_external=True)
        assert r.status_code == 428 and r.json()["type"] == "/problems/confirm-high-risk"
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


def test_memory_keeper_proposes_facts_canon_needs_author(writer):
    p = writer.project()
    c = writer.post(f"/v1/projects/{p['id']}/characters", json={"canonical_name": "مريم"}).json()
    ch = writer.node(p["id"], "chapter", "ف", meta={"story_time": 1960})
    writer.write(ch["document_id"], "كانت مريم في العاشرة من عمرها.")
    writer.run(p["id"], "A08")
    prop = next(x for x in _props(writer, p["id"]) if x["kind"] == "fact")
    assert prop["patch"]["object"]["value"] == 1950 and prop["patch"]["subject_id"] == c["id"]
    r = writer.post(f"/v1/proposals/{prop['id']}/accept", json={"as_canon": True}).json()
    fact = writer.get(f"/v1/projects/{p['id']}/facts").json()["items"][0]
    assert fact["id"] == r["result"]["fact_id"] and fact["epistemic_status"] == "canon" and fact["origin"] == "agent"


def test_disabling_agents_per_project(novel):
    w, p, ch = novel
    w.patch(f"/v1/projects/{p['id']}", json={"ai_enabled": False})
    r = w.run(p["id"], "A11")
    assert r.status_code == 409 and r.json()["type"] == "/problems/agents-disabled"
    assert w.write(ch["document_id"], "الكتابة مستمرة").status_code == 200
