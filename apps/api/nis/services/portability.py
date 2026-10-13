"""Full data export (FR24, AT21) and verified restore (AT17).

The archive is self-describing: manifest.json (format version + SHA-256 per file), project.json (every
project-scoped table), sources/ (original uploaded files) and manuscript.md (human-readable text). Restore
creates a *new* project with fresh IDs (no collision with live data) and verifies every checksum first.
"""

from __future__ import annotations

import io
import json
import uuid
import zipfile
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from ..errors import bad_request
from ..models import (
    Assessment,
    CanonFact,
    Character,
    Citation,
    Comment,
    Conflict,
    Document,
    EntityEdge,
    Event,
    Manuscript,
    Membership,
    Node,
    Place,
    Project,
    Proposal,
    Revision,
    SourceChunk,
    SourceFile,
    StyleProfile,
)
from ..security import sha256_hex
from ..storage import store
from .exports import compile_book, to_markdown
from .manuscript import canonical_hash

FORMAT = "nis-project-archive/1"
# Order matters for restore (parents before children).
TABLES: list[tuple[str, Any]] = [
    ("manuscripts", Manuscript), ("nodes", Node), ("documents", Document), ("revisions", Revision),
    ("characters", Character), ("places", Place), ("events", Event), ("entity_edges", EntityEdge),
    ("canon_facts", CanonFact), ("conflicts", Conflict), ("source_files", SourceFile),
    ("source_chunks", SourceChunk), ("citations", Citation), ("proposals", Proposal),
    ("assessments", Assessment), ("comments", Comment), ("style_profiles", StyleProfile),
]
SKIP_ON_RESTORE = {"proposals"}  # proposals reference runs that are not portable; they are exported for record


def _row(obj: Any) -> dict[str, Any]:
    out = {}
    for col in inspect(obj).mapper.column_attrs:
        v = getattr(obj, col.key)
        if isinstance(v, uuid.UUID):
            v = str(v)
        elif isinstance(v, datetime):
            v = v.isoformat()
        out[col.key] = v
    return out


def export_archive(db: Session, project: Project) -> bytes:
    data: dict[str, Any] = {"project": _row(project), "tables": {}}
    for name, model in TABLES:
        rows = db.scalars(select(model).where(model.project_id == project.id)).all()
        data["tables"][name] = [_row(r) for r in rows]
    files: dict[str, bytes] = {}
    for s in db.scalars(select(SourceFile).where(SourceFile.project_id == project.id)):
        try:
            files[f"sources/{s.id}.{s.file_type}"] = store().get(s.object_key)
        except FileNotFoundError:
            pass
    files["project.json"] = json.dumps(data, ensure_ascii=False, indent=1).encode("utf-8")
    files["manuscript.md"] = to_markdown(compile_book(db, project))
    files["README.txt"] = (
        "أرشيف مشروع من استوديو ذكاء الرواية (NIS)\n"
        "project.json: كل بيانات المشروع (المخطوط، المراجعات كاملة، الكتاب المقدس للقصة، المصادر، الاستشهادات، "
        "التعارضات، المقترحات، التقييمات).\n"
        "sources/: الملفات الأصلية المرفوعة.\nmanuscript.md: النص المجمّع للقراءة.\n"
        "manifest.json: بصمات SHA-256 للتحقق من سلامة الأرشيف قبل الاسترجاع.\n"
        "الاحتفاظ: الحذف من التطبيق نهائي؛ النسخ الاحتياطية لقاعدة البيانات تُدار حسب سياسة المشغّل الموثقة "
        "في docs/operations.md.\n"
    ).encode()
    manifest = {
        "format": FORMAT, "exported_at": datetime.now(UTC).isoformat(), "project_id": str(project.id),
        "files": {k: sha256_hex(v) for k, v in files.items()},
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=1))
        for k, v in files.items():
            z.writestr(k, v)
    return buf.getvalue()


def _remap(value: Any, ids: dict[str, str]) -> Any:
    if isinstance(value, str):
        return ids.get(value, value)
    if isinstance(value, list):
        return [_remap(v, ids) for v in value]
    if isinstance(value, dict):
        return {k: _remap(v, ids) for k, v in value.items()}
    return value


def _coerce(model: Any, row: dict[str, Any]) -> dict[str, Any]:
    out = {}
    cols = {c.key: c for c in inspect(model).column_attrs}
    for k, v in row.items():
        if k not in cols:
            continue
        typ = cols[k].columns[0].type
        try:
            pyt = typ.python_type
        except NotImplementedError:
            pyt = None
        if v is not None and pyt is uuid.UUID:
            v = uuid.UUID(v)
        elif v is not None and pyt is datetime:
            v = datetime.fromisoformat(v)
        out[k] = v
    return out


def import_archive(db: Session, raw: bytes, owner_id: uuid.UUID) -> Project:
    try:
        z = zipfile.ZipFile(io.BytesIO(raw))
        manifest = json.loads(z.read("manifest.json"))
    except (zipfile.BadZipFile, KeyError, json.JSONDecodeError) as e:
        raise bad_request("الأرشيف غير صالح أو ناقص.") from e
    if manifest.get("format") != FORMAT:
        raise bad_request("صيغة الأرشيف غير مدعومة.")
    for name, digest in manifest.get("files", {}).items():
        if sha256_hex(z.read(name)) != digest:
            raise bad_request(f"فشل التحقق من سلامة الملف {name} — الأرشيف تالف أو معدّل.")
    data = json.loads(z.read("project.json"))
    ids: dict[str, str] = {}
    old_pid = data["project"]["id"]
    for _name, rows in data["tables"].items():
        for r in rows:
            ids[r["id"]] = str(uuid.uuid4())
    ids[old_pid] = str(uuid.uuid4())

    p = data["project"]
    project = Project(
        id=uuid.UUID(ids[old_pid]), owner_id=owner_id, title=p["title"] + " (مستعاد)", language=p["language"],
        genre=p.get("genre", ""), description=p.get("description", ""), logline=p.get("logline", ""),
        privacy_mode=p.get("privacy_mode", "private"), word_goal=p.get("word_goal", 0),
        ai_enabled=p.get("ai_enabled", True), nlqi_weights=p.get("nlqi_weights") or {},
    )
    db.add(project)
    db.flush()
    db.add(Membership(user_id=owner_id, project_id=project.id, role="owner"))
    db.flush()
    pending_docs: list[tuple[Document, str | None]] = []
    for name, model in TABLES:
        if name in SKIP_ON_RESTORE:
            continue
        rows = sorted(data["tables"].get(name, []),
                      key=lambda r: (r.get("parent_id") is not None, r.get("revision_no", 0)))
        if name == "nodes":  # insert parents before children
            rows = _topo(rows)
        for r in rows:
            r = _remap(r, ids)
            if name == "revisions" and canonical_hash(r["content_json"]) != r["checksum"]:
                raise bad_request("بصمة إحدى المراجعات لا تطابق محتواها — رُفض الاسترجاع.")
            for k in ("created_by", "approved_by", "resolved_by", "decided_by", "uploaded_by", "updated_by",
                      "rater_id", "author_id", "owner_id", "requested_by"):
                if k in r and r[k] is not None:
                    r[k] = str(owner_id)
            r["project_id"] = str(project.id)
            if name == "source_files":
                fname = f"sources/{_inv(ids, r['id'])}.{r['file_type']}"
                key = f"projects/{project.id}/sources/{r['id']}.{r['file_type']}"
                if fname in z.namelist():
                    store().put(key, z.read(fname))
                r["object_key"] = key
            if name == "documents":
                cur = r.pop("current_revision_id", None)
                obj = model(**_coerce(model, r))
                db.add(obj)
                pending_docs.append((obj, cur))
                continue
            if name == "citations":
                r["created_by"] = str(owner_id)
            db.add(model(**_coerce(model, r)))
        db.flush()
    for doc, cur in pending_docs:
        doc.current_revision_id = uuid.UUID(cur) if cur else None
    db.flush()
    return project


def _inv(ids: dict[str, str], new: str) -> str:
    for k, v in ids.items():
        if v == new:
            return k
    return new


def _topo(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {r["id"]: r for r in rows}
    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    def visit(r: dict[str, Any]) -> None:
        if r["id"] in seen:
            return
        pid = r.get("parent_id")
        if pid and pid in by_id:
            visit(by_id[pid])
        seen.add(r["id"])
        out.append(r)

    for r in rows:
        visit(r)
    return out
