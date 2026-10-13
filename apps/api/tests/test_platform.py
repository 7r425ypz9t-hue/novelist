"""Migrations match the models, admin console, OpenAPI contract, performance smoke (AT15)."""

import os
import time

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

from nis.db import Base, get_engine


def test_migrations_are_in_sync_with_models():
    with get_engine().connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == [], diff


def test_openapi_is_3_1_and_versioned(client):
    spec = client.get("/v1/openapi.json").json()
    assert spec["openapi"].startswith("3.1")
    assert all(path.startswith("/v1/") for path in spec["paths"])


def test_admin_console_masks_private_projects(client, make_writer):
    from sqlalchemy import update

    from nis.db import SessionLocal
    from nis.models import User

    admin = make_writer("admin")
    db = SessionLocal()
    db.execute(update(User).where(User.email == admin.email).values(is_admin=True))
    db.commit()
    db.close()
    owner = make_writer("author")
    owner.project("عنوان حساس جداً", privacy_mode="private")
    h = admin.get("/v1/admin/health").json()
    assert h["database"]["ok"] and h["storage"]["ok"] and h["provider"]["name"] == "disabled"
    titles = [x["title"] for x in admin.get("/v1/admin/projects").json()["items"]]
    assert "عنوان حساس جداً" not in titles and "🔒 مشروع خاص" in titles
    m = admin.get("/v1/admin/metrics").json()
    assert m["projects"] >= 1 and "runs" in m
    assert admin.get("/v1/admin/audit", params={"action": "project."}).json()["items"]


FULL = os.environ.get("NIS_PERF_FULL") == "1"


@pytest.mark.skipif(not FULL and os.environ.get("CI") == "true", reason="perf smoke runs locally / nightly")
def test_AT15_long_manuscript_performance(writer):
    """150k words / 30 chapters (full) or 45k words (smoke). Times are recorded, thresholds per NFR01/02."""
    from nis.text import doc_from_plain

    chapters = 30 if FULL else 9
    para = "كان البحر يتنفس ببطء والمدينة تنام على صوته بينما يعدّ نادر السفن العائدة واحدةً واحدة في المساء. "
    chapter_text = "\n\n".join(para * 5 for _ in range(100))  # ≈ 5,000 words per chapter
    p = writer.project("اختبار الحمل")
    big_doc = None
    timings = {}
    t0 = time.perf_counter()
    for i in range(chapters):
        ch = writer.node(p["id"], "chapter", f"فصل {i + 1}")
        writer.write(ch["document_id"], chapter_text)
        big_doc = big_doc or ch["document_id"]
    timings["write_all"] = time.perf_counter() - t0
    total = writer.get(f"/v1/projects/{p['id']}/dashboard").json()["words"]
    assert total >= chapters * 4900

    # NFR01: open a 10k-word chapter < 2 s
    v = writer.get(f"/v1/documents/{big_doc}").json()["version"]
    ten_k = doc_from_plain("\n\n".join(para * 10 for _ in range(100)))
    t = time.perf_counter()
    r = writer.put(f"/v1/documents/{big_doc}", headers={"If-Match": f'W/"{v}"'}, json={"content_json": ten_k})
    timings["save_10k"] = time.perf_counter() - t
    assert r.status_code == 200 and r.json()["word_count"] >= 9800
    t = time.perf_counter()
    assert writer.get(f"/v1/documents/{big_doc}").status_code == 200
    timings["open_10k"] = time.perf_counter() - t
    assert timings["open_10k"] < 2.0
    assert timings["save_10k"] < 2.0

    t = time.perf_counter()
    assert writer.post(f"/v1/projects/{p['id']}/continuity/scan").status_code == 200
    timings["continuity_scan"] = time.perf_counter() - t
    t = time.perf_counter()
    r = writer.get(f"/v1/projects/{p['id']}/manuscript/search", params={"q": "السفن", "whole_word": True})
    timings["manuscript_search"] = time.perf_counter() - t
    assert r.status_code == 200 and r.json()["total"] >= chapters * 500
    assert timings["manuscript_search"] < 2.0
    t = time.perf_counter()
    assert writer.post(f"/v1/projects/{p['id']}/exports", json={"format": "docx"}).status_code == 201
    timings["export_docx"] = time.perf_counter() - t
    print("\nAT15 timings (s):", {k: round(v, 3) for k, v in timings.items()}, "words:", total)


@pytest.mark.skipif(os.environ.get("NIS_PERF_FULL") != "1", reason="heavy load test: set NIS_PERF_FULL=1")
def test_NFR04_thousand_scenes_three_hundred_characters():
    """NFR04 load shape: 1,000 scenes, 300 characters. Seeded directly through the service layer, then the
    continuity scan and the full A00 analysis run over it. Times are printed, not asserted beyond sanity."""
    import uuid as _uuid

    from nis.agents import orchestrator
    from nis.db import SessionLocal
    from nis.models import Character, Manuscript, Membership, Project, User
    from nis.security import hash_password
    from nis.services.continuity import run_scan
    from nis.services.manuscript import create_node
    from nis.text import doc_from_plain

    db = SessionLocal()
    u = User(email=f"load-{_uuid.uuid4().hex[:6]}@example.test", password_hash=hash_password("x" * 12))
    db.add(u)
    db.flush()
    p = Project(owner_id=u.id, title="حمل")
    db.add(p)
    db.flush()
    db.add(Membership(user_id=u.id, project_id=p.id, role="owner"))
    m = Manuscript(project_id=p.id, title="حمل")
    db.add(m)
    db.flush()
    names = [f"شخصية{i:03d}" for i in range(300)]
    for i, n in enumerate(names):
        db.add(Character(project_id=p.id, canonical_name=n, profile={"birth_year": 1900 + i % 50}))
    t0 = time.perf_counter()
    for c in range(50):
        ch = create_node(db, manuscript=m, parent=None, node_type="chapter", title=f"ف{c}", position=None, user_id=u.id)
        for s in range(20):
            k = c * 20 + s
            text = (f"كان {names[k % 300]} في العاشرة من عمره حين التقى {names[(k * 7) % 300]} عند البحر. "
                    "ثم مضى الليل طويلاً والموج يضرب الصخور. ") * 6
            create_node(db, manuscript=m, parent=ch, node_type="scene", title="", position=None, user_id=u.id,
                        content=doc_from_plain(text), meta={"story_time": 1910 + c})
    db.commit()
    seed = time.perf_counter() - t0
    t = time.perf_counter()
    stats = run_scan(db, p.id)
    db.commit()
    scan = time.perf_counter() - t
    run, _ = orchestrator.create_run(db, project=p, user_id=u.id, agent_id="A00", skills=None, goal="", scope={},
                                     idempotency_key=_uuid.uuid4().hex, use_model=False,
                                     acknowledge_external=False, confirm_high_risk=False)
    db.commit()
    t = time.perf_counter()
    orchestrator.execute(run.id)
    full = time.perf_counter() - t
    db.refresh(run)
    db.close()
    assert run.status == "succeeded", run.error
    print(f"\nNFR04: seed {seed:.1f}s · continuity scan {scan:.1f}s ({stats['found']} conflicts) · A00 full run {full:.1f}s")
