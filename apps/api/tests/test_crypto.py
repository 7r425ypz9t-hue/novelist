"""Encryption at rest: ciphertext in the database, plaintext through the API, legacy rows still readable."""

import json

from sqlalchemy import text

from nis import crypto
from nis.db import get_engine


def _raw(sql, **params):
    with get_engine().connect() as c:
        return c.execute(text(sql), params).all()


def test_manuscript_is_ciphertext_at_rest_and_plaintext_via_api(writer):
    assert crypto.enabled()  # conftest sets a test-only NIS_MASTER_KEY
    p = writer.project()
    ch = writer.node(p["id"], "chapter", "فصل")
    assert writer.write(ch["document_id"], "جملة سرية عن البحر لا يراها من يسرق النسخة الاحتياطية").status_code == 200
    rows = [r for r in _raw("SELECT content_json, text_plain, document_id FROM revisions")
            if str(r[2]).replace("-", "") == ch["document_id"].replace("-", "")]
    assert rows and all(r[0].startswith(crypto.PREFIX) and r[1].startswith(crypto.PREFIX) for r in rows)
    assert all("سرية" not in r[0] + r[1] for r in rows)
    assert "سرية" in writer.get(f"/v1/documents/{ch['document_id']}").json()["content_json"]["content"][0]["content"][0]["text"]


def test_legacy_plaintext_is_readable_and_migratable(writer, monkeypatch):
    monkeypatch.delenv("NIS_MASTER_KEY")
    crypto.reset()
    try:
        p = writer.project()
        ch = writer.node(p["id"], "chapter", "فصل")
        writer.write(ch["document_id"], "نص قديم غير مشفر")  # written before a key existed
    finally:
        monkeypatch.undo()
        crypto.reset()
    assert any(not r[0].startswith(crypto.PREFIX) for r in _raw("SELECT text_plain FROM revisions"))
    assert "قديم" in json.dumps(writer.get(f"/v1/documents/{ch['document_id']}").json(), ensure_ascii=False)
    from nis.cli import encrypt_existing

    done = encrypt_existing()
    assert done["revisions"] >= 1
    assert not [r for r in _raw("SELECT text_plain FROM revisions") if not r[0].startswith(crypto.PREFIX)]
    assert "قديم" in json.dumps(writer.get(f"/v1/documents/{ch['document_id']}").json(), ensure_ascii=False)
