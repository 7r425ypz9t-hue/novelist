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
    para = "كان البحر يتنفس ببطء والمدينة تنام على صوته بينما يعدّ سالم السفن العائدة واحدةً واحدة في المساء. "
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
    assert writer.post(f"/v1/projects/{p['id']}/exports", json={"format": "docx"}).status_code == 201
    timings["export_docx"] = time.perf_counter() - t
    print("\nAT15 timings (s):", {k: round(v, 3) for k, v in timings.items()}, "words:", total)
