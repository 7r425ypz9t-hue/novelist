"""Operator commands: readiness check (`nis doctor`), data verification (`nis verify-data`), scripted admin."""

import io
import json
import uuid

from sqlalchemy import text

from nis import crypto
from nis.cli import main
from nis.db import get_engine
from nis.ops import FAIL, OK, doctor, verify_data


def _by_key(checks):
    return {c.key: c for c in checks}


def test_doctor_reports_a_ready_installation(writer, capsys):
    p = writer.project("رواية الجاهزية")
    ch = writer.node(p["id"], "chapter", "الأول")
    assert writer.write(ch["document_id"], "نصٌّ أصلي للاختبار.").status_code == 200
    checks = _by_key(doctor())
    assert checks["database"].status == OK and checks["migrations"].status == OK
    assert checks["storage"].status == OK and checks["fonts"].status == OK
    assert checks["encryption"].status == OK and "يفتح" in checks["encryption"].detail
    assert checks["provider"].status == OK
    assert main(["doctor", "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert {"key", "status", "title", "detail"} <= set(out[0])
    assert "نصٌّ أصلي" not in json.dumps(out, ensure_ascii=False)  # never prints manuscript content


def test_doctor_blocks_start_when_the_key_does_not_open_stored_content(writer, monkeypatch):
    p = writer.project("رواية المفتاح")
    ch = writer.node(p["id"], "chapter", "الأول")
    assert writer.write(ch["document_id"], "سطر مشفّر.").status_code == 200
    monkeypatch.setenv("NIS_MASTER_KEY", crypto.new_key())
    crypto.reset()
    try:
        enc = _by_key(doctor())["encryption"]
        assert enc.status == FAIL and "ليس هو المفتاح" in enc.detail
        assert main(["doctor"]) == 1
        r = verify_data()
        assert r["ok"] is False and r["unreadable_rows"] >= 2
        monkeypatch.delenv("NIS_MASTER_KEY")
        crypto.reset()
        assert _by_key(doctor())["encryption"].status == FAIL  # encrypted rows, no key at all
    finally:
        monkeypatch.undo()
        crypto.reset()


def test_verify_data_detects_a_revision_whose_content_no_longer_matches(writer):
    p = writer.project("رواية السلامة")
    ch = writer.node(p["id"], "chapter", "الأول")
    assert writer.write(ch["document_id"], "نص سليم.").status_code == 200
    assert verify_data()["ok"] is True
    with get_engine().begin() as c:
        rid, checksum = c.execute(text("SELECT id, checksum FROM revisions ORDER BY created_at DESC LIMIT 1")).one()
        c.execute(text("UPDATE revisions SET checksum = :x WHERE id = :i"), {"x": "0" * 64, "i": rid})
    try:
        r = verify_data()
        assert r["ok"] is False and r["checksum_mismatches"] == 1
    finally:
        with get_engine().begin() as c:
            c.execute(text("UPDATE revisions SET checksum = :x WHERE id = :i"), {"x": checksum, "i": rid})


def test_create_admin_reads_password_from_stdin(monkeypatch, client):
    email = f"ops-{uuid.uuid4().hex[:6]}@example.test"
    monkeypatch.setattr("sys.stdin", io.StringIO("a-long-enough-password\n"))
    assert main(["create-admin", email, "--password-stdin"]) == 0
    r = client.post("/v1/auth/login", json={"email": email, "password": "a-long-enough-password"})
    assert r.status_code == 200
    monkeypatch.setattr("sys.stdin", io.StringIO("short\n"))
    assert main(["create-admin", f"x{email}", "--password-stdin"]) == 2
