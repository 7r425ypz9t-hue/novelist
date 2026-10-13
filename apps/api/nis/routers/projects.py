"""Projects, members, consents, manuscript tree, documents, revisions, comments, import, dashboard."""

import io
import re
import uuid
from collections import defaultdict
from datetime import timedelta

from fastapi import APIRouter, Depends, File, Header, Query, Response, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import audit
from ..config import get_settings
from ..db import get_db
from ..deps import Access, current_user, document_access, node_access, project_access
from ..errors import ProblemError, bad_request, conflict, not_found
from ..models import (
    AgentRun,
    Citation,
    Comment,
    Conflict,
    Consent,
    Document,
    Manuscript,
    Membership,
    Node,
    Project,
    Proposal,
    Revision,
    SourceFile,
    User,
    utcnow,
)
from ..schemas import (
    CommentIn,
    ConsentIn,
    DocumentPut,
    ImportCommitIn,
    ManuscriptIn,
    ManuscriptPatch,
    MemberIn,
    NodeIn,
    NodePatch,
    ProjectIn,
    ProjectPatch,
    ReorderIn,
)
from ..services.manuscript import (
    create_node,
    document_out,
    etag,
    labels,
    move_node,
    node_out,
    ordered_nodes,
    parse_if_match,
    revision_out,
    save_document,
)
from ..text import arabic_pattern, count_words, find_spans, diff_texts, diff_stats, doc_from_plain

router = APIRouter(prefix="/v1", tags=["manuscript"])


def project_out(p: Project, role: str | None = None) -> dict:
    return {
        "id": str(p.id), "title": p.title, "language": p.language, "genre": p.genre, "description": p.description,
        "logline": p.logline, "privacy_mode": p.privacy_mode, "status": p.status, "word_goal": p.word_goal,
        "ai_enabled": p.ai_enabled, "role": role, "created_at": p.created_at.isoformat(),
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


def _uuid(v: str | None, what: str = "المعرف") -> uuid.UUID | None:
    if v is None:
        return None
    try:
        return uuid.UUID(str(v))
    except ValueError as e:
        raise bad_request(f"{what} غير صالح.") from e


# ───────────────────────── projects ─────────────────────────


@router.get("/projects")
def list_projects(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.execute(select(Project, Membership.role).join(Membership, Membership.project_id == Project.id)
                      .where(Membership.user_id == user.id).order_by(Project.updated_at.desc())).all()
    out = []
    for p, role in rows:
        words = db.scalar(select(func.coalesce(func.sum(Document.word_count), 0))
                          .join(Node, Node.id == Document.node_id)
                          .where(Document.project_id == p.id, Node.deleted_at.is_(None)))
        out.append({**project_out(p, role), "words": int(words or 0)})
    return {"items": out}


@router.post("/projects", status_code=201)
def create_project(body: ProjectIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = Project(owner_id=user.id, title=body.title, language=body.language, genre=body.genre,
                description=body.description, logline=body.logline, privacy_mode=body.privacy_mode,
                word_goal=body.word_goal)
    db.add(p)
    db.flush()
    db.add(Membership(user_id=user.id, project_id=p.id, role="owner"))
    m = Manuscript(project_id=p.id, title=body.manuscript_title or body.title, author_name=body.author_name)
    db.add(m)
    audit.record(db, "project.create", actor_id=user.id, project_id=p.id, object_type="project", object_id=p.id)
    db.commit()
    return {**project_out(p, "owner"), "manuscript_id": str(m.id)}


@router.get("/projects/{project_id}")
def get_project(acc: Access = Depends(project_access), db: Session = Depends(get_db)):
    ms = db.scalars(select(Manuscript).where(Manuscript.project_id == acc.project.id).order_by(Manuscript.position))
    return {**project_out(acc.project, acc.role), "permissions": sorted(acc.perms),
            "manuscripts": [{"id": str(m.id), "title": m.title, "subtitle": m.subtitle, "author_name": m.author_name}
                            for m in ms]}


@router.patch("/projects/{project_id}")
def patch_project(body: ProjectPatch, acc: Access = Depends(project_access), db: Session = Depends(get_db)):
    acc.require("manage")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(acc.project, k, v)
    audit.record(db, "project.update", actor_id=acc.user.id, project_id=acc.project.id, object_type="project",
                 object_id=acc.project.id, meta={"fields": ",".join(body.model_dump(exclude_unset=True))})
    db.commit()
    return project_out(acc.project, acc.role)


@router.get("/projects/{project_id}/members")
def list_members(acc: Access = Depends(project_access), db: Session = Depends(get_db)):
    rows = db.execute(select(Membership, User).join(User, User.id == Membership.user_id)
                      .where(Membership.project_id == acc.project.id)).all()
    return {"items": [{"user_id": str(u.id), "email": u.email if acc.role == "owner" else "",
                       "display_name": u.display_name, "role": m.role, "permissions": m.permissions}
                      for m, u in rows]}


@router.post("/projects/{project_id}/members", status_code=201)
def add_member(body: MemberIn, acc: Access = Depends(project_access), db: Session = Depends(get_db)):
    acc.require("manage")
    u = db.scalar(select(User).where(User.email == body.email.strip().lower()))
    if not u:
        raise not_found("المستخدم")
    if db.scalar(select(Membership).where(Membership.project_id == acc.project.id, Membership.user_id == u.id)):
        raise conflict("المستخدم عضو بالفعل.")
    db.add(Membership(user_id=u.id, project_id=acc.project.id, role=body.role, permissions=body.permissions))
    audit.record(db, "member.add", actor_id=acc.user.id, project_id=acc.project.id, object_type="user",
                 object_id=u.id, meta={"role": body.role})
    db.commit()
    return {"user_id": str(u.id), "role": body.role}


@router.delete("/projects/{project_id}/members/{user_id}", status_code=204)
def remove_member(user_id: uuid.UUID, acc: Access = Depends(project_access), db: Session = Depends(get_db)):
    acc.require("manage")
    m = db.scalar(select(Membership).where(Membership.project_id == acc.project.id, Membership.user_id == user_id))
    if not m or m.role == "owner":
        raise not_found("العضوية")
    db.delete(m)
    audit.record(db, "member.remove", actor_id=acc.user.id, project_id=acc.project.id, object_id=user_id)
    db.commit()


# ───────────────────────── consents ─────────────────────────


@router.get("/projects/{project_id}/consents")
def list_consents(acc: Access = Depends(project_access), db: Session = Depends(get_db)):
    rows = db.scalars(select(Consent).where(Consent.project_id == acc.project.id, Consent.user_id == acc.user.id))
    return {"items": [{"id": str(c.id), "kind": c.kind, "scope": c.scope, "granted_at": c.granted_at.isoformat(),
                       "revoked_at": c.revoked_at.isoformat() if c.revoked_at else None} for c in rows]}


@router.post("/projects/{project_id}/consents", status_code=201)
def grant_consent(body: ConsentIn, acc: Access = Depends(project_access), db: Session = Depends(get_db)):
    acc.require("manage")
    from ..agents.providers import get_provider

    desc = get_provider().describe()
    c = Consent(user_id=acc.user.id, project_id=acc.project.id, kind=body.kind,
                scope={"destination": desc["destination"], "provider": desc["name"], "model": desc.get("model"),
                       "acknowledged": body.acknowledge_destination})
    db.add(c)
    audit.record(db, "consent.grant", actor_id=acc.user.id, project_id=acc.project.id, object_type="consent",
                 meta={"kind": body.kind, "destination": desc["destination"]})
    db.commit()
    return {"id": str(c.id), "scope": c.scope}


@router.delete("/projects/{project_id}/consents/{consent_id}", status_code=204)
def revoke_consent(consent_id: uuid.UUID, acc: Access = Depends(project_access), db: Session = Depends(get_db)):
    c = db.get(Consent, consent_id)
    if not c or c.project_id != acc.project.id or c.user_id != acc.user.id:
        raise not_found("الموافقة")
    c.revoked_at = utcnow()
    audit.record(db, "consent.revoke", actor_id=acc.user.id, project_id=acc.project.id, object_id=consent_id)
    db.commit()


# ───────────────────────── manuscripts & tree ─────────────────────────


@router.post("/projects/{project_id}/manuscripts", status_code=201)
def add_manuscript(body: ManuscriptIn, acc: Access = Depends(project_access), db: Session = Depends(get_db)):
    acc.require("write")
    n = db.scalar(select(func.count()).select_from(Manuscript).where(Manuscript.project_id == acc.project.id)) or 0
    m = Manuscript(project_id=acc.project.id, title=body.title, subtitle=body.subtitle, author_name=body.author_name,
                   position=n)
    db.add(m)
    db.commit()
    return {"id": str(m.id), "title": m.title}


@router.patch("/manuscripts/{manuscript_id}")
def patch_manuscript(manuscript_id: uuid.UUID, body: ManuscriptPatch, user: User = Depends(current_user),
                     db: Session = Depends(get_db)):
    from ..deps import access_for

    m = db.get(Manuscript, manuscript_id)
    if not m:
        raise not_found("المخطوط")
    access_for(db, user, m.project_id).require("write")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(m, k, v)
    db.commit()
    return {"id": str(m.id), "title": m.title, "subtitle": m.subtitle, "author_name": m.author_name}


@router.get("/projects/{project_id}/tree")
def tree(acc: Access = Depends(project_access), db: Session = Depends(get_db)):
    out = []
    docs = {d.node_id: d for d in db.scalars(select(Document).where(Document.project_id == acc.project.id))}
    for m in db.scalars(select(Manuscript).where(Manuscript.project_id == acc.project.id).order_by(Manuscript.position)):
        nodes = ordered_nodes(db, m.id)
        lb = labels(nodes)
        out.append({"manuscript": {"id": str(m.id), "title": m.title, "subtitle": m.subtitle,
                                   "author_name": m.author_name},
                    "nodes": [{**node_out(n, docs.get(n.id)), "label": lb.get(n.id, "")} for n in nodes]})
    return {"manuscripts": out}


def _snippet(text: str, start: int, end: int, ctx: int = 40) -> dict:
    """Context inside the hit's own paragraph; cut flags tell the client where to draw an ellipsis."""
    para_start = text.rfind("\n", 0, start) + 1
    para_end = text.find("\n", end)
    para_end = len(text) if para_end < 0 else para_end
    b0, a1 = max(para_start, start - ctx), min(para_end, end + ctx)
    return {"before": text[b0:start], "match": text[start:end], "after": text[end:a1], "offset": start,
            "cut_before": b0 > para_start, "cut_after": a1 < para_end}


@router.get("/projects/{project_id}/manuscript/search")
def manuscript_search(q: str = Query(min_length=1, max_length=200), ignore_marks: bool = True,
                      unify_letters: bool = True, whole_word: bool = False, clitics: bool = True,
                      acc: Access = Depends(project_access), db: Session = Depends(get_db)):
    """Read-only, Arabic-aware find across every live unit of the project, in reading order."""
    pat = arabic_pattern(q, ignore_marks=ignore_marks, unify_letters=unify_letters, whole_word=whole_word,
                         clitics=clitics)
    if pat is None:
        raise bad_request("عبارة البحث فارغة")
    docs = {d.node_id: d for d in db.scalars(select(Document).where(Document.project_id == acc.project.id))}
    items, total, max_snips = [], 0, 20
    for m in db.scalars(select(Manuscript).where(Manuscript.project_id == acc.project.id).order_by(Manuscript.position)):
        nodes = ordered_nodes(db, m.id)
        lb = labels(nodes)
        for n in nodes:
            d = docs.get(n.id)
            if d is None or not d.text_plain:
                continue
            text = d.text_plain
            found = find_spans(pat, text)
            if not found:
                continue
            total += len(found)
            snips = [_snippet(text, a, b) for a, b in found[:max_snips]]
            items.append({"node_id": str(n.id), "document_id": str(d.id), "type": n.type, "title": n.title,
                          "label": lb.get(n.id, ""), "count": len(found), "snippets": snips})
    return {"query": q, "total": total, "units": len(items), "items": items}


@router.post("/projects/{project_id}/nodes", status_code=201)
def add_node(body: NodeIn, acc: Access = Depends(project_access), db: Session = Depends(get_db)):
    acc.require("write")
    if body.manuscript_id:
        m = db.get(Manuscript, _uuid(body.manuscript_id))
    else:
        m = db.scalar(select(Manuscript).where(Manuscript.project_id == acc.project.id).order_by(Manuscript.position))
    if not m or m.project_id != acc.project.id:
        raise not_found("المخطوط")
    parent = None
    if body.parent_id:
        parent = db.get(Node, _uuid(body.parent_id))
        if not parent or parent.manuscript_id != m.id:
            raise not_found("العقدة الأم")
    n = create_node(db, manuscript=m, parent=parent, node_type=body.type, title=body.title, position=body.position,
                    user_id=acc.user.id, meta=body.meta)
    audit.record(db, "node.create", actor_id=acc.user.id, project_id=acc.project.id, object_type=body.type,
                 object_id=n.id)
    db.commit()
    doc = db.scalar(select(Document).where(Document.node_id == n.id))
    return node_out(n, doc)


@router.patch("/nodes/{node_id}")
def patch_node(node_id: uuid.UUID, body: NodePatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    node, acc = node_access(db, user, node_id)
    acc.require("write")
    data = body.model_dump(exclude_unset=True)
    if "meta" in data:
        meta = dict(node.meta or {})
        meta.update(data.pop("meta") or {})
        node.meta = {k: v for k, v in meta.items() if v is not None and v != ""}
    for k, v in data.items():
        setattr(node, k, v)
    db.commit()
    return node_out(node, db.scalar(select(Document).where(Document.node_id == node.id)))


@router.patch("/nodes/{node_id}/reorder")
def reorder(node_id: uuid.UUID, body: ReorderIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    node, acc = node_access(db, user, node_id)
    acc.require("write")
    parent = db.get(Node, _uuid(body.parent_id)) if body.parent_id else None
    if body.parent_id and (not parent or parent.project_id != acc.project.id):
        raise not_found("العقدة الأم")
    move_node(db, node, parent, body.position)
    audit.record(db, "node.move", actor_id=user.id, project_id=acc.project.id, object_type=node.type, object_id=node.id)
    db.commit()
    return node_out(node)


@router.delete("/nodes/{node_id}")
def delete_node(node_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Move a node (and its subtree) to the trash. Nothing is erased; restore brings it back."""
    node, acc = node_access(db, user, node_id)
    acc.require("write")
    if node.deleted_at is not None:
        raise not_found("العقدة")
    now = utcnow()
    stack, moved = [node], 0
    while stack:
        n = stack.pop()
        n.deleted_at = now
        moved += 1
        stack.extend(db.scalars(select(Node).where(Node.parent_id == n.id, Node.deleted_at.is_(None))))
    db.flush()
    from ..services.manuscript import siblings

    for i, s in enumerate(siblings(db, node.manuscript_id, node.parent_id)):
        s.position = i
    audit.record(db, "node.trash", actor_id=user.id, project_id=acc.project.id, object_type=node.type,
                 object_id=node_id, meta={"nodes": moved})
    db.commit()
    return {"trashed": moved}


@router.get("/projects/{project_id}/trash")
def trash(acc: Access = Depends(project_access), db: Session = Depends(get_db)):
    rows = db.scalars(select(Node).where(Node.project_id == acc.project.id, Node.deleted_at.is_not(None))
                      .order_by(Node.deleted_at.desc()))
    return {"items": [{**node_out(n), "deleted_at": n.deleted_at.isoformat()} for n in rows]}


@router.post("/nodes/{node_id}/restore")
def restore_node(node_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    node, acc = node_access(db, user, node_id)
    acc.require("write")
    if node.deleted_at is None:
        raise conflict("العقدة ليست في سلة المحذوفات.")
    if node.parent_id:
        parent = db.get(Node, node.parent_id)
        if parent is not None and parent.deleted_at is not None:
            raise conflict("استعد العقدة الأم أولاً.")
    stamp = node.deleted_at
    stack = [node]
    while stack:
        n = stack.pop()
        n.deleted_at = None
        stack.extend(db.scalars(select(Node).where(Node.parent_id == n.id, Node.deleted_at == stamp)))
    from ..services.manuscript import siblings

    sibs = siblings(db, node.manuscript_id, node.parent_id)
    sibs = [x for x in sibs if x.id != node.id] + [node]
    for i, s in enumerate(sibs):
        s.position = i
    audit.record(db, "node.restore", actor_id=user.id, project_id=acc.project.id, object_id=node_id)
    db.commit()
    return node_out(node)


# ───────────────────────── documents & revisions ─────────────────────────


@router.get("/documents/{document_id}")
def get_document(document_id: uuid.UUID, response: Response, user: User = Depends(current_user),
                 db: Session = Depends(get_db)):
    doc, _ = document_access(db, user, document_id)
    response.headers["ETag"] = etag(doc)
    return document_out(doc)


@router.put("/documents/{document_id}")
def put_document(document_id: uuid.UUID, body: DocumentPut, response: Response,
                 if_match: str | None = Header(default=None), user: User = Depends(current_user),
                 db: Session = Depends(get_db)):
    doc, acc = document_access(db, user, document_id)
    acc.require("write")
    expected = parse_if_match(if_match)
    if expected is None:
        raise ProblemError(428, "If-Match مطلوب", "أرسل رقم النسخة التي عدّلتها في ترويسة If-Match.",
                           "/problems/precondition-required")
    rev, created = save_document(db, doc, body.content_json, user_id=user.id, kind=body.kind, label=body.label,
                                 client_save_id=body.client_save_id, expected_version=expected)
    if created:
        audit.record(db, "document.save", actor_id=user.id, project_id=doc.project_id, object_type="document",
                     object_id=doc.id, meta={"revision_no": rev.revision_no, "kind": body.kind, "words": rev.word_count})
    db.commit()
    response.headers["ETag"] = etag(doc)
    return {**document_out(doc), "revision": revision_out(rev), "created": created}


@router.get("/documents/{document_id}/revisions")
def list_revisions(document_id: uuid.UUID, limit: int = 50, before: int | None = None,
                   user: User = Depends(current_user), db: Session = Depends(get_db)):
    doc, _ = document_access(db, user, document_id)
    q = select(Revision).where(Revision.document_id == doc.id)
    if before:
        q = q.where(Revision.revision_no < before)
    rows = list(db.scalars(q.order_by(Revision.revision_no.desc()).limit(min(max(limit, 1), 200))))
    return {"items": [revision_out(r) for r in rows],
            "next_before": rows[-1].revision_no if len(rows) == limit else None}


@router.get("/revisions/{revision_id}")
def get_revision(revision_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    r = db.get(Revision, revision_id)
    if not r:
        raise not_found("المراجعة")
    document_access(db, user, r.document_id)
    return revision_out(r, with_content=True)


@router.get("/documents/{document_id}/diff")
def diff(document_id: uuid.UUID, a: uuid.UUID, b: uuid.UUID | None = None, user: User = Depends(current_user),
         db: Session = Depends(get_db)):
    doc, _ = document_access(db, user, document_id)
    ra = db.get(Revision, a)
    if not ra or ra.document_id != doc.id:
        raise not_found("المراجعة")
    if b:
        rb = db.get(Revision, b)
        if not rb or rb.document_id != doc.id:
            raise not_found("المراجعة")
        tb, label_b = rb.text_plain, f"#{rb.revision_no}"
    else:
        tb, label_b = doc.text_plain, "الحالية"
    segs = diff_texts(ra.text_plain, tb)
    return {"a": f"#{ra.revision_no}", "b": label_b, "segments": segs, "stats": diff_stats(segs)}


@router.post("/revisions/{revision_id}/restore")
def restore(revision_id: uuid.UUID, if_match: str | None = Header(default=None), user: User = Depends(current_user),
            db: Session = Depends(get_db)):
    r = db.get(Revision, revision_id)
    if not r:
        raise not_found("المراجعة")
    doc, acc = document_access(db, user, r.document_id)
    acc.require("write")
    rev, _ = save_document(db, doc, r.content_json, user_id=user.id, kind="restore",
                           label=f"استعادة المراجعة #{r.revision_no}", expected_version=parse_if_match(if_match))
    audit.record(db, "revision.restore", actor_id=user.id, project_id=doc.project_id, object_type="revision",
                 object_id=r.id, meta={"new_revision_no": rev.revision_no})
    db.commit()
    return {**document_out(doc), "revision": revision_out(rev)}


# ───────────────────────── comments ─────────────────────────


@router.get("/documents/{document_id}/comments")
def list_comments(document_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    doc, _ = document_access(db, user, document_id)
    rows = db.execute(select(Comment, User.display_name).join(User, User.id == Comment.author_id)
                      .where(Comment.document_id == doc.id).order_by(Comment.created_at)).all()
    return {"items": [{"id": str(c.id), "author": name, "body": c.body, "anchor": c.anchor, "state": c.state,
                       "created_at": c.created_at.isoformat()} for c, name in rows]}


@router.post("/documents/{document_id}/comments", status_code=201)
def add_comment(document_id: uuid.UUID, body: CommentIn, user: User = Depends(current_user),
                db: Session = Depends(get_db)):
    doc, acc = document_access(db, user, document_id)
    acc.require("comment")
    c = Comment(project_id=doc.project_id, document_id=doc.id, author_id=user.id, body=body.body, anchor=body.anchor)
    db.add(c)
    db.commit()
    return {"id": str(c.id)}


# ───────────────────────── import (FR21) ─────────────────────────

CHAPTER_HEAD = re.compile(r"^\s*(?:#{1,2}\s+.+|(?:الفصل|فصل|الباب)\s+\S+.*|chapter\s+\S+.*)\s*$", re.IGNORECASE)


def split_chapters(units: list[tuple[str, bool]]) -> list[dict]:
    chapters: list[dict] = []
    cur = {"title": "", "paras": []}
    for text, is_heading in units:
        if is_heading or (len(text) < 80 and CHAPTER_HEAD.match(text)):
            if cur["paras"] or cur["title"]:
                chapters.append(cur)
            cur = {"title": text.lstrip("# ").strip(), "paras": []}
        else:
            cur["paras"].append(text)
    if cur["paras"] or cur["title"]:
        chapters.append(cur)
    return [{"title": c["title"] or f"فصل {i + 1}", "text": "\n\n".join(c["paras"]),
             "words": count_words("\n\n".join(c["paras"]))} for i, c in enumerate(chapters)]


@router.post("/projects/{project_id}/import/preview")
async def import_preview(file: UploadFile = File(...), acc: Access = Depends(project_access)):
    acc.require("write")
    data = await file.read()
    if len(data) > get_settings().max_upload_mb * 1024 * 1024:
        raise ProblemError(413, "الملف كبير", "تجاوز الحد المسموح للرفع.", "/problems/too-large")
    name = (file.filename or "").lower()
    units: list[tuple[str, bool]] = []
    if name.endswith(".docx"):
        import docx

        if not data.startswith(b"PK"):
            raise bad_request("ملف DOCX غير صالح.")
        d = docx.Document(io.BytesIO(data))
        for p in d.paragraphs:
            if p.text.strip():
                units.append((p.text.strip(), (p.style.name or "").lower().startswith(("heading", "title"))))
    elif name.endswith((".md", ".txt")):
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as e:
            raise bad_request("الملف يجب أن يكون UTF-8.") from e
        for p in re.split(r"\n\s*\n|\n(?=#)", text.replace("\r\n", "\n")):
            p = p.strip()
            if p:
                lines = p.split("\n")
                if CHAPTER_HEAD.match(lines[0]) and len(lines) > 1:
                    units.append((lines[0], True))
                    units.append(("\n".join(lines[1:]).strip(), False))
                else:
                    units.append((p, name.endswith(".md") and p.startswith("#")))
    else:
        raise bad_request("الاستيراد يدعم DOCX وMD وTXT.")
    chapters = split_chapters(units)
    return {"filename": file.filename, "chapters": chapters, "total_words": sum(c["words"] for c in chapters)}


@router.post("/projects/{project_id}/import/commit", status_code=201)
def import_commit(body: ImportCommitIn, acc: Access = Depends(project_access), db: Session = Depends(get_db)):
    acc.require("write")
    m = db.get(Manuscript, _uuid(body.manuscript_id)) if body.manuscript_id else db.scalar(
        select(Manuscript).where(Manuscript.project_id == acc.project.id).order_by(Manuscript.position))
    if not m or m.project_id != acc.project.id:
        raise not_found("المخطوط")
    created = []
    for ch in body.chapters:
        n = create_node(db, manuscript=m, parent=None, node_type="chapter", title=str(ch.get("title", ""))[:300],
                        position=None, user_id=acc.user.id, content=doc_from_plain(str(ch.get("text", ""))))
        created.append(str(n.id))
    audit.record(db, "manuscript.import", actor_id=acc.user.id, project_id=acc.project.id,
                 meta={"chapters": len(created)})
    db.commit()
    return {"created": created}


# ───────────────────────── dashboard (FR23) ─────────────────────────


@router.get("/projects/{project_id}/dashboard")
def dashboard(acc: Access = Depends(project_access), db: Session = Depends(get_db)):
    pid = acc.project.id
    docs = list(db.scalars(select(Document).join(Node, Node.id == Document.node_id)
                           .where(Document.project_id == pid, Node.deleted_at.is_(None))))
    words = sum(d.word_count for d in docs)
    nodes = list(db.scalars(select(Node).where(Node.project_id == pid, Node.deleted_at.is_(None))))
    status = defaultdict(int)
    for n in nodes:
        if n.type == "scene":
            status[n.status] += 1
    per_chapter = []
    for m in db.scalars(select(Manuscript).where(Manuscript.project_id == pid).order_by(Manuscript.position)):
        ordered = ordered_nodes(db, m.id)
        lb = labels(ordered)
        by_node = {d.node_id: d for d in docs}
        for n in ordered:
            if n.type == "chapter":
                kids = [x for x in ordered if x.parent_id == n.id]
                w = (by_node[n.id].word_count if n.id in by_node else 0) + sum(
                    by_node[k.id].word_count for k in kids if k.id in by_node)
                per_chapter.append({"node_id": str(n.id), "label": lb.get(n.id, n.title), "words": w,
                                    "scenes": len(kids)})
    conflicts = defaultdict(int)
    for sev, cnt in db.execute(select(Conflict.severity, func.count()).where(
            Conflict.project_id == pid, Conflict.state == "open").group_by(Conflict.severity)):
        conflicts[sev] = cnt
    pending = db.scalar(select(func.count()).select_from(Proposal).where(Proposal.project_id == pid,
                                                                       Proposal.state == "pending")) or 0
    runs = db.scalars(select(AgentRun).where(AgentRun.project_id == pid).order_by(AgentRun.created_at.desc()).limit(6))
    since = utcnow() - timedelta(days=30)
    # daily net words written = sum of positive word deltas between consecutive revisions
    revs = db.execute(select(Revision.document_id, Revision.word_count, Revision.created_at)
                      .where(Revision.project_id == pid).order_by(Revision.document_id, Revision.revision_no)).all()
    last: dict = {}
    daily: dict[str, int] = defaultdict(int)
    for did, wc, at in revs:
        prev = last.get(did, 0)
        last[did] = wc
        at_aware = at if at.tzinfo else at.replace(tzinfo=since.tzinfo)
        if at_aware >= since and wc > prev:
            daily[at_aware.date().isoformat()] += wc - prev
    sources = db.scalar(select(func.count()).select_from(SourceFile).where(SourceFile.project_id == pid)) or 0
    unverified = db.scalar(select(func.count()).select_from(Citation).where(
        Citation.project_id == pid, Citation.verification_state == "unverified")) or 0
    empty_scenes = sum(1 for d in docs if d.word_count == 0)
    return {
        "project": project_out(acc.project, acc.role),
        "words": words, "word_goal": acc.project.word_goal,
        "progress": round(words / acc.project.word_goal, 4) if acc.project.word_goal else None,
        "counts": {"parts": sum(1 for n in nodes if n.type == "part"),
                   "chapters": sum(1 for n in nodes if n.type == "chapter"),
                   "scenes": sum(1 for n in nodes if n.type == "scene"), "empty_units": empty_scenes,
                   "sources": sources, "unverified_citations": unverified},
        "scene_status": dict(status), "per_chapter": per_chapter,
        "open_conflicts": {"high": conflicts["high"], "medium": conflicts["medium"], "low": conflicts["low"]},
        "pending_proposals": pending,
        "recent_runs": [{"id": str(r.id), "agent_id": r.agent_id, "status": r.status,
                         "created_at": r.created_at.isoformat()} for r in runs],
        "daily_words": [{"date": k, "words": v} for k, v in sorted(daily.items())],
    }
