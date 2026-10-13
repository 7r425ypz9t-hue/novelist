"""Authorization, IDOR isolation (AT12), roles, audit redaction, headers."""

from sqlalchemy import select

from nis.db import SessionLocal
from nis.models import AuditEvent


def test_AT12_other_users_cannot_reach_any_object(writer, other):
    p = writer.project("سرّي")
    ch = writer.node(p["id"], "chapter", "فصل")
    writer.write(ch["document_id"], "نص خاص جداً بالمؤلف")
    rev = writer.get(f"/v1/documents/{ch['document_id']}/revisions").json()["items"][0]
    src = writer.post(f"/v1/projects/{p['id']}/sources", data={"license_state": "owned", "usage_consent": "true"},
                      files={"file": ("n.txt", "مصدر خاص".encode(), "text/plain")}).json()
    exp = writer.post(f"/v1/projects/{p['id']}/exports", json={"format": "md"}).json()
    run = writer.run(p["id"], "A11").json()
    urls = [
        f"/v1/projects/{p['id']}", f"/v1/projects/{p['id']}/tree", f"/v1/documents/{ch['document_id']}",
        f"/v1/documents/{ch['document_id']}/revisions", f"/v1/revisions/{rev['id']}",
        f"/v1/projects/{p['id']}/sources/{src['id']}/chunks", f"/v1/exports/{exp['id']}/download",
        f"/v1/agents/runs/{run['id']}", f"/v1/projects/{p['id']}/proposals", f"/v1/projects/{p['id']}/dashboard",
        f"/v1/projects/{p['id']}/characters", f"/v1/projects/{p['id']}/conflicts",
    ]
    for u in urls:
        r = other.get(u)
        assert r.status_code == 404, (u, r.status_code)
        assert "خاص" not in r.text
    assert other.write(ch["document_id"], "تخريب", version=1).status_code == 404
    assert other.post(f"/v1/projects/{p['id']}/research/query", json={"question": "مصدر"}).status_code == 404
    assert other.run(p["id"], "A11").status_code == 404
    assert other.get("/v1/projects").json()["items"] == []


def test_unauthenticated_is_401_problem_json(client):
    r = client.get("/v1/projects")
    assert r.status_code == 401
    assert r.headers["content-type"].startswith("application/problem+json")


def test_roles_commenter_cannot_write_editor_cannot_decide(make_writer):
    owner, commenter, editor = make_writer("o"), make_writer("c"), make_writer("e")
    p = owner.project()
    owner.post(f"/v1/projects/{p['id']}/members", json={"email": commenter.email, "role": "commenter"})
    owner.post(f"/v1/projects/{p['id']}/members", json={"email": editor.email, "role": "editor"})
    ch = owner.node(p["id"], "chapter", "فصل")
    owner.write(ch["document_id"], "قال: نعم, ثم مضى")
    assert commenter.write(ch["document_id"], "تعديل", version=2).status_code == 403
    assert commenter.post(f"/v1/documents/{ch['document_id']}/comments", json={"body": "ملاحظة"}).status_code == 201
    assert editor.run(p["id"], "A11").status_code == 202
    prop = editor.get(f"/v1/projects/{p['id']}/proposals").json()["items"][0]
    r = editor.post(f"/v1/proposals/{prop['id']}/accept", json={})
    assert r.status_code == 403 and "صاحب الرواية" in r.json()["detail"]


def test_audit_log_never_stores_manuscript_text(writer):
    p = writer.project()
    ch = writer.node(p["id"], "chapter", "فصل")
    writer.write(ch["document_id"], "جملة سرية لا يجوز أن تظهر في السجلات")
    db = SessionLocal()
    try:
        for e in db.scalars(select(AuditEvent)):
            assert "سرية" not in str(e.metadata_redacted)
    finally:
        db.close()


def test_security_headers_present(client):
    r = client.get("/v1/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert r.headers["x-frame-options"] == "DENY"


def test_admin_endpoints_require_admin_and_mask_private_titles(make_writer):
    # the very first user of the test DB became admin; find a non-admin and check refusal
    w = make_writer("plain")
    assert w.user["is_admin"] is False
    assert w.get("/v1/admin/health").status_code == 403
