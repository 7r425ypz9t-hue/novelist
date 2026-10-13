"""Manuscript tree, documents and immutable revisions."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..errors import ProblemError, bad_request
from ..models import Document, Manuscript, Node, Revision, utcnow
from ..security import sha256_hex
from ..text import count_words, doc_to_plain, empty_doc, sanitize_doc

ALLOWED_PARENT = {"part": {None}, "chapter": {None, "part"}, "scene": {"chapter"}}
TYPE_AR = {"part": "الجزء", "chapter": "الفصل", "scene": "المشهد"}


def canonical_hash(content: dict[str, Any]) -> str:
    import json

    return sha256_hex(json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def etag(doc: Document) -> str:
    return f'W/"{doc.version}"'


def parse_if_match(value: str | None) -> int | None:
    if not value:
        return None
    v = value.strip()
    if v.startswith("W/"):
        v = v[2:]
    v = v.strip('"')
    try:
        return int(v)
    except ValueError:
        return None


def siblings(db: Session, manuscript_id: uuid.UUID, parent_id: uuid.UUID | None) -> list[Node]:
    q = select(Node).where(Node.manuscript_id == manuscript_id, Node.deleted_at.is_(None))
    q = q.where(Node.parent_id.is_(None)) if parent_id is None else q.where(Node.parent_id == parent_id)
    return list(db.scalars(q.order_by(Node.position, Node.created_at)))


def _validate_parent(node_type: str, parent: Node | None) -> None:
    if node_type not in ALLOWED_PARENT:
        raise bad_request("نوع العقدة يجب أن يكون part أو chapter أو scene.")
    ptype = parent.type if parent else None
    if ptype not in ALLOWED_PARENT[node_type]:
        raise bad_request(f"لا يمكن وضع {TYPE_AR[node_type]} داخل {TYPE_AR.get(ptype or '', 'الجذر')}.")


def create_node(
    db: Session, *, manuscript: Manuscript, parent: Node | None, node_type: str, title: str,
    position: int | None, user_id: uuid.UUID, meta: dict[str, Any] | None = None,
    content: dict[str, Any] | None = None,
) -> Node:
    _validate_parent(node_type, parent)
    sibs = siblings(db, manuscript.id, parent.id if parent else None)
    pos = len(sibs) if position is None else max(0, min(position, len(sibs)))
    node = Node(
        project_id=manuscript.project_id, manuscript_id=manuscript.id, parent_id=parent.id if parent else None,
        type=node_type, title=title, position=pos, meta=meta or {},
    )
    db.add(node)
    db.flush()
    sibs.insert(pos, node)
    for i, s in enumerate(sibs):
        s.position = i
    if node_type in ("chapter", "scene"):
        doc = Document(project_id=manuscript.project_id, node_id=node.id)
        db.add(doc)
        db.flush()
        save_document(db, doc, content or empty_doc(), user_id=user_id, kind="checkpoint", label="إنشاء",
                      author_type="import" if content else "human")
    return node


def move_node(db: Session, node: Node, new_parent: Node | None, position: int) -> None:
    if new_parent is not None:
        if new_parent.manuscript_id != node.manuscript_id:
            raise bad_request("لا يمكن النقل بين مخطوطين مختلفين.")
        p: Node | None = new_parent
        while p is not None:
            if p.id == node.id:
                raise bad_request("لا يمكن نقل عقدة داخل نفسها.")
            p = db.get(Node, p.parent_id) if p.parent_id else None
    _validate_parent(node.type, new_parent)
    old = siblings(db, node.manuscript_id, node.parent_id)
    old = [s for s in old if s.id != node.id]
    for i, s in enumerate(old):
        s.position = i
    node.parent_id = new_parent.id if new_parent else None
    db.flush()
    sibs = [s for s in siblings(db, node.manuscript_id, node.parent_id) if s.id != node.id]
    pos = max(0, min(position, len(sibs)))
    sibs.insert(pos, node)
    for i, s in enumerate(sibs):
        s.position = i


def ordered_nodes(db: Session, manuscript_id: uuid.UUID) -> list[Node]:
    """Depth-first reading order."""
    all_nodes = list(db.scalars(select(Node).where(Node.manuscript_id == manuscript_id, Node.deleted_at.is_(None))))
    by_parent: dict[uuid.UUID | None, list[Node]] = {}
    for n in all_nodes:
        by_parent.setdefault(n.parent_id, []).append(n)
    for lst in by_parent.values():
        lst.sort(key=lambda n: (n.position, n.created_at))
    out: list[Node] = []

    def walk(pid: uuid.UUID | None) -> None:
        for n in by_parent.get(pid, []):
            out.append(n)
            walk(n.id)

    walk(None)
    return out


def labels(nodes: list[Node]) -> dict[uuid.UUID, str]:
    """Human labels: «الفصل 3 · المشهد 2» — computed from reading order, never stored."""
    out: dict[uuid.UUID, str] = {}
    ch = 0
    sc: dict[uuid.UUID, int] = {}
    for n in nodes:
        if n.type == "part":
            out[n.id] = n.title or "جزء"
        elif n.type == "chapter":
            ch += 1
            out[n.id] = f"الفصل {ch}" + (f" — {n.title}" if n.title else "")
        elif n.type == "scene":
            k = n.parent_id or n.id
            sc[k] = sc.get(k, 0) + 1
            parent_label = out.get(n.parent_id, "") if n.parent_id else ""
            out[n.id] = f"{parent_label.split(' — ')[0]} · المشهد {sc[k]}".strip(" ·")
    return out


def save_document(
    db: Session, doc: Document, content: dict[str, Any], *, user_id: uuid.UUID | None, kind: str,
    label: str = "", author_type: str = "human", client_save_id: str | None = None,
    expected_version: int | None = None, source_proposal_id: uuid.UUID | None = None,
) -> tuple[Revision, bool]:
    """Persist a new immutable revision. Returns (revision, created).

    * `expected_version` mismatch → 412-style conflict (never overwrite someone else's save; AT04).
    * Same `client_save_id` replayed (offline queue, retries) → returns the original revision (idempotent).
    * Identical content → no new revision unless it is an explicit checkpoint.
    """
    if client_save_id:
        prev = db.scalar(select(Revision).where(Revision.document_id == doc.id,
                                                Revision.client_save_id == client_save_id))
        if prev:
            return prev, False
    if expected_version is not None and expected_version != doc.version:
        raise ProblemError(
            412, "تعارض نسخة", "تعارض نسخة: حُفظت نسخة أحدث من هذا المستند بعد آخر تحميل لديك. لن يُكتب فوقها؛ "
            "راجع الفروق وادمج يدوياً.", "/problems/version-conflict",
            current_version=doc.version, current_revision_id=str(doc.current_revision_id),
        )
    clean = sanitize_doc(content)
    h = canonical_hash(clean)
    if h == doc.content_hash and kind == "autosave" and doc.current_revision_id:
        rev = db.get(Revision, doc.current_revision_id)
        if rev:
            return rev, False
    plain = doc_to_plain(clean)
    n = (db.scalar(select(func.max(Revision.revision_no)).where(Revision.document_id == doc.id)) or 0) + 1
    rev = Revision(
        project_id=doc.project_id, document_id=doc.id, revision_no=n, parent_revision_id=doc.current_revision_id,
        kind=kind, author_type=author_type, created_by=user_id, label=label[:200], content_json=clean,
        text_plain=plain, checksum=h, word_count=count_words(plain), client_save_id=client_save_id,
        source_proposal_id=source_proposal_id,
    )
    db.add(rev)
    db.flush()
    doc.content_json, doc.text_plain, doc.content_hash = clean, plain, h
    doc.word_count = rev.word_count
    doc.version += 1
    doc.current_revision_id = rev.id
    doc.updated_at = utcnow()
    doc.updated_by = user_id
    return rev, True


def document_out(doc: Document) -> dict[str, Any]:
    return {
        "id": str(doc.id), "node_id": str(doc.node_id), "project_id": str(doc.project_id),
        "content_json": doc.content_json, "version": doc.version, "etag": etag(doc),
        "word_count": doc.word_count, "content_hash": doc.content_hash,
        "current_revision_id": str(doc.current_revision_id) if doc.current_revision_id else None,
        "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
    }


def revision_out(r: Revision, with_content: bool = False) -> dict[str, Any]:
    d = {
        "id": str(r.id), "document_id": str(r.document_id), "revision_no": r.revision_no, "kind": r.kind,
        "author_type": r.author_type, "label": r.label, "checksum": r.checksum, "word_count": r.word_count,
        "created_by": str(r.created_by) if r.created_by else None, "created_at": r.created_at.isoformat(),
        "parent_revision_id": str(r.parent_revision_id) if r.parent_revision_id else None,
        "source_proposal_id": str(r.source_proposal_id) if r.source_proposal_id else None,
    }
    if with_content:
        d["content_json"] = r.content_json
        d["text_plain"] = r.text_plain
    return d


def node_out(n: Node, doc: Document | None = None) -> dict[str, Any]:
    return {
        "id": str(n.id), "manuscript_id": str(n.manuscript_id), "parent_id": str(n.parent_id) if n.parent_id else None,
        "type": n.type, "title": n.title, "position": n.position, "status": n.status, "meta": n.meta or {},
        "document_id": str(doc.id) if doc else None, "word_count": doc.word_count if doc else 0,
    }
