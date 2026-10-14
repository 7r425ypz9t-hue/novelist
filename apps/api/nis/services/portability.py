"""Full data export (FR24, AT21) and verified restore (AT17).

The archive is self-describing: manifest.json (format version + SHA-256 per file), project.json (every
project-scoped table), sources/ (original uploaded files) and manuscript.md (human-readable text). Every checksum
is verified before anything is written.

Two ways in:
* `import_archive` — a project this server does not have keeps its IDs (the same novel moved to another computer
  stays the same novel, so later archives can update it); if the project already exists here, the archive is
  restored as an independent copy with fresh IDs.
* `merge_archive` — brings an archive of the SAME project (from the writer's other computer) into the existing
  one without overwriting anything: see its docstring.
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
        "أرشيف مشروع من تطبيق «كاتب»\n"
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


def _open(raw: bytes) -> tuple[zipfile.ZipFile, dict[str, Any], dict[str, Any]]:
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
    return z, manifest, json.loads(z.read("project.json"))


def import_archive(db: Session, raw: bytes, owner_id: uuid.UUID) -> Project:
    z, _manifest, data = _open(raw)
    ids: dict[str, str] = {}
    old_pid = data["project"]["id"]
    # same novel on another computer → same IDs; already here → an independent copy with fresh IDs
    keep = db.get(Project, uuid.UUID(old_pid)) is None
    for _name, rows in data["tables"].items():
        for r in rows:
            ids[r["id"]] = r["id"] if keep else str(uuid.uuid4())
    ids[old_pid] = old_pid if keep else str(uuid.uuid4())

    p = data["project"]
    project = Project(
        id=uuid.UUID(ids[old_pid]), owner_id=owner_id, title=p["title"] if keep else p["title"] + " (مستعاد)",
        language=p["language"],
        genre=p.get("genre", ""), description=p.get("description", ""), logline=p.get("logline", ""),
        privacy_mode=p.get("privacy_mode", "private"), word_goal=p.get("word_goal", 0),
        ai_enabled=p.get("ai_enabled", True), nlqi_weights=p.get("nlqi_weights") or {},
        calendars=p.get("calendars"),
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


USER_FIELDS = ("created_by", "approved_by", "resolved_by", "decided_by", "uploaded_by", "updated_by", "rater_id",
               "author_id", "owner_id", "requested_by")
MERGE_SKIP = {"proposals", "revisions", "documents"}  # proposals are not portable; text has its own rules below
FOREIGN_LABEL = "من جهاز آخر — لم تُدمج تلقائياً"


def _ancestors(rev_id: str | None, parent_of: dict[str, str | None]) -> set[str]:
    seen: set[str] = set()
    while rev_id and rev_id not in seen:
        seen.add(rev_id)
        rev_id = parent_of.get(rev_id)
    return seen


def merge_archive(db: Session, raw: bytes, project: Project, user_id: uuid.UUID) -> dict[str, Any]:
    """Update THIS project from an archive of the same novel exported on another computer. Nothing is overwritten:

    * revisions are immutable: missing ones are appended to history (renumbered if the number is taken here);
    * a unit's text moves forward only when the other computer's version descends from the one here
      (fast-forward). If this computer is ahead, it stays. If both changed independently, this computer's text
      stays and the other version is kept in history, labelled, to compare and restore by hand;
    * other records: missing ones are added; existing ones take the other computer's values only if it changed
      them more recently (updated_at), which covers titles, order, scene matrix, story bible and trash moves.
    """
    from ..models import utcnow

    z, manifest, data = _open(raw)
    if manifest.get("project_id") != str(project.id) or data["project"]["id"] != str(project.id):
        from ..errors import ProblemError

        raise ProblemError(409, "أرشيف لمشروع آخر",
                           "هذا الأرشيف لرواية أخرى (أو لنسخة مستقلة منها). للتحديث صدّر الأرشيف من المشروع نفسه "
                           "على جهازك الآخر، أو استورده مشروعاً جديداً.", "/problems/archive-other-project")
    pid = str(project.id)
    added: dict[str, int] = {}
    updated: dict[str, int] = {}

    def prep(name: str, r: dict[str, Any]) -> dict[str, Any]:
        r = dict(r)
        for k in USER_FIELDS:
            if k in r and r[k] is not None:
                r[k] = str(user_id)
        r["project_id"] = pid
        return r

    def newer(a: Any, b: Any) -> bool:
        if not a or not b:
            return False
        a = datetime.fromisoformat(a) if isinstance(a, str) else a
        b = datetime.fromisoformat(b) if isinstance(b, str) else b
        a = a if a.tzinfo else a.replace(tzinfo=UTC)
        b = b if b.tzinfo else b.replace(tzinfo=UTC)
        return a > b

    # 1 · plain records
    for name, model in TABLES:
        if name in MERGE_SKIP:
            continue
        rows = data["tables"].get(name, [])
        if name == "nodes":
            rows = _topo(rows)
        for r in rows:
            r = prep(name, r)
            local = db.get(model, uuid.UUID(r["id"]))
            if local is None:
                if name == "source_files":
                    fname = f"sources/{r['id']}.{r['file_type']}"
                    key = f"projects/{pid}/sources/{r['id']}.{r['file_type']}"
                    if fname in z.namelist():
                        store().put(key, z.read(fname))
                    r["object_key"] = key
                db.add(model(**_coerce(model, r)))
                added[name] = added.get(name, 0) + 1
            elif str(getattr(local, "project_id", pid)) == pid and hasattr(local, "updated_at") \
                    and newer(r.get("updated_at"), local.updated_at):
                vals = _coerce(model, r)
                for k, v in vals.items():
                    if k not in ("id", "project_id", "created_at", "object_key"):
                        setattr(local, k, v)
                updated[name] = updated.get(name, 0) + 1
        db.flush()

    # 2 · revisions: append what is missing (immutable history)
    arch_revs = data["tables"].get("revisions", [])
    parent_of = {r["id"]: r.get("parent_revision_id") for r in arch_revs}
    known = {str(x) for x in db.scalars(select(Revision.id).where(Revision.project_id == project.id))}
    arch_docs = {d["id"]: d for d in data["tables"].get("documents", [])}
    local_docs = {str(d.id): d for d in db.scalars(select(Document).where(Document.project_id == project.id))}

    # documents that do not exist here yet (new units from the other computer)
    for did, d in arch_docs.items():
        if did not in local_docs:
            d = prep("documents", d)
            d.pop("current_revision_id", None)
            doc = Document(**_coerce(Document, d))
            db.add(doc)
            local_docs[did] = doc
            added["documents"] = added.get("documents", 0) + 1
    db.flush()

    diverged_heads: set[str] = set()
    for did, d in arch_docs.items():
        here = local_docs[did]
        cur = str(here.current_revision_id) if here.current_revision_id else None
        ahead = d.get("current_revision_id")
        if ahead and cur and ahead not in known and cur not in _ancestors(ahead, parent_of):
            diverged_heads.add(ahead)

    from sqlalchemy import func

    for r in sorted(arch_revs, key=lambda x: (x["document_id"], x.get("revision_no", 0))):
        if r["id"] in known:
            continue
        if canonical_hash(r["content_json"]) != r["checksum"]:
            raise bad_request("بصمة إحدى المراجعات لا تطابق محتواها — رُفض الدمج.")
        r = prep("revisions", r)
        taken = db.scalar(select(Revision.id).where(Revision.document_id == uuid.UUID(r["document_id"]),
                                                    Revision.revision_no == r["revision_no"]))
        if taken is not None:
            r["revision_no"] = (db.scalar(select(func.max(Revision.revision_no))
                                          .where(Revision.document_id == uuid.UUID(r["document_id"]))) or 0) + 1
        if r.get("client_save_id") and db.scalar(select(Revision.id).where(
                Revision.document_id == uuid.UUID(r["document_id"]), Revision.client_save_id == r["client_save_id"])):
            r["client_save_id"] = None
        if r["id"] in diverged_heads:
            r["label"] = (FOREIGN_LABEL + (" · " + r["label"] if r.get("label") else ""))[:200]
        db.add(Revision(**_coerce(Revision, r)))
        db.flush()
        added["revisions"] = added.get("revisions", 0) + 1

    # 3 · move each unit's text forward only along its own history
    report_docs: dict[str, list] = {"fast_forward": [], "kept_local": [], "diverged": [], "new": []}
    node_title = {str(n.id): n.title for n in db.scalars(select(Node).where(Node.project_id == project.id))}
    for did, d in arch_docs.items():
        here = local_docs[did]
        ahead = d.get("current_revision_id")
        cur = str(here.current_revision_id) if here.current_revision_id else None
        label = node_title.get(str(here.node_id), "") or "وحدة"
        if not ahead or ahead == cur:
            continue
        if cur is None or cur in _ancestors(ahead, parent_of):
            rev = db.get(Revision, uuid.UUID(ahead))
            here.content_json, here.text_plain, here.content_hash = rev.content_json, rev.text_plain, rev.checksum
            here.word_count, here.current_revision_id = rev.word_count, rev.id
            here.version += 1
            here.updated_at, here.updated_by = utcnow(), user_id
            report_docs["new" if cur is None else "fast_forward"].append({"node_id": str(here.node_id), "title": label})
        elif ahead in known:
            report_docs["kept_local"].append({"node_id": str(here.node_id), "title": label})
        else:
            report_docs["diverged"].append({"node_id": str(here.node_id), "title": label, "revision_id": ahead})
    p = data["project"]
    if newer(p.get("updated_at"), project.updated_at):
        for k in ("title", "genre", "description", "logline", "word_goal", "privacy_mode", "calendars"):
            if k in p:
                setattr(project, k, p[k])
        updated["project"] = 1
    db.flush()
    return {"added": added, "updated": updated, "documents": report_docs,
            "exported_at": manifest.get("exported_at")}
