"""Proposal decisions. Only a human with `decide_proposals` reaches this module (owner by default)."""

from __future__ import annotations

import copy
import uuid
from typing import Any

from sqlalchemy.orm import Session

from .. import audit
from ..errors import ProblemError, bad_request, conflict
from ..models import CanonFact, Document, Proposal, Revision, utcnow
from ..text import PatchMismatch, apply_ops, diff_texts, doc_to_plain
from .manuscript import save_document


def preview(db: Session, p: Proposal) -> dict[str, Any]:
    if p.kind != "patch" or not p.document_id:
        return {"applicable": True, "diff": []}
    doc = db.get(Document, p.document_id)
    base = db.get(Revision, p.target_revision_id) if p.target_revision_id else None
    source = base.content_json if base else (doc.content_json if doc else {})
    try:
        new = apply_ops(source, p.patch.get("ops", []))
        return {"applicable": True, "stale": bool(doc and doc.current_revision_id != p.target_revision_id),
                "diff": diff_texts(doc_to_plain(source), doc_to_plain(new))}
    except PatchMismatch as e:
        return {"applicable": False, "stale": True, "error": str(e), "diff": []}


def accept(db: Session, p: Proposal, user_id: uuid.UUID, *, edited_ops: list[dict[str, Any]] | None = None,
           allow_rebase: bool = False, as_canon: bool = False, note: str = "") -> dict[str, Any]:
    if p.state != "pending":
        raise conflict(f"المقترح ليس معلقاً (الحالة: {p.state}).")
    result: dict[str, Any] = {}
    if p.kind == "patch":
        doc = db.get(Document, p.document_id) if p.document_id else None
        if not doc:
            raise bad_request("المستند المستهدف لم يعد موجوداً.")
        ops = p.patch.get("ops", [])
        if edited_ops is not None:  # "Modify": the author may change the replacement text only
            if len(edited_ops) != len(ops):
                raise bad_request("التعديل يجب أن يحافظ على عدد العمليات وأماكنها.")
            merged = []
            for a, b in zip(ops, edited_ops, strict=True):
                m = copy.deepcopy(a)
                if "text" in b and a.get("op") in ("replace_text", "insert_block"):
                    m["text"] = str(b["text"])
                merged.append(m)
            ops = merged
        if doc.current_revision_id != p.target_revision_id and not allow_rebase:
            raise ProblemError(
                409, "تعارض نسخة",
                "تغيّر المستند بعد إنشاء المقترح. لن يُطبَّق قسراً؛ اختر «تطبيق على النسخة الحالية» إن كان المقطع "
                "ما يزال مطابقاً، أو ارفض المقترح وأعد التشغيل.", "/problems/stale-proposal",
                current_revision_id=str(doc.current_revision_id), target_revision_id=str(p.target_revision_id))
        try:
            new_content = apply_ops(doc.content_json, ops)
        except PatchMismatch as e:
            p.state = "stale"
            raise conflict(f"لا يمكن تطبيق المقترح: {e}. أُعلِم المقترح بأنه متقادم.") from e
        rev, _ = save_document(db, doc, new_content, user_id=user_id, kind="proposal",
                               label=f"قبول مقترح {p.agent_id}/{p.skill_id}", author_type="human_accepted_ai",
                               source_proposal_id=p.id)
        p.result_revision_id = rev.id
        result["revision_id"] = str(rev.id)
        result["modified"] = edited_ops is not None
    elif p.kind == "fact":
        pl = p.patch
        f = CanonFact(
            project_id=p.project_id, subject_type=pl.get("subject_type", "world"),
            subject_id=uuid.UUID(pl["subject_id"]) if pl.get("subject_id") else None,
            subject_label=pl.get("subject_label", ""), predicate=pl.get("predicate", ""),
            object=pl.get("object") or {}, statement=pl.get("statement", ""),
            epistemic_status="canon" if as_canon else "draft", source_refs=p.evidence_refs, origin="agent",
            approved_by=user_id if as_canon else None, approved_at=utcnow() if as_canon else None,
        )
        db.add(f)
        db.flush()
        result["fact_id"] = str(f.id)
    p.state, p.decided_by, p.decided_at, p.decision_note = "accepted", user_id, utcnow(), note[:2000]
    audit.record(db, "proposal.accept", actor_id=user_id, project_id=p.project_id, object_type="proposal",
                 object_id=p.id, meta={"kind": p.kind, "skill": p.skill_id, "modified": edited_ops is not None})
    return result


def reject(db: Session, p: Proposal, user_id: uuid.UUID, note: str = "") -> None:
    if p.state != "pending" and p.state != "stale":
        raise conflict(f"المقترح ليس معلقاً (الحالة: {p.state}).")
    p.state, p.decided_by, p.decided_at, p.decision_note = "rejected", user_id, utcnow(), note[:2000]
    audit.record(db, "proposal.reject", actor_id=user_id, project_id=p.project_id, object_type="proposal",
                 object_id=p.id, meta={"skill": p.skill_id})


def proposal_out(p: Proposal) -> dict[str, Any]:
    return {
        "id": str(p.id), "run_id": str(p.run_id) if p.run_id else None, "agent_id": p.agent_id,
        "skill_id": p.skill_id, "kind": p.kind, "document_id": str(p.document_id) if p.document_id else None,
        "target_revision_id": str(p.target_revision_id) if p.target_revision_id else None, "patch": p.patch,
        "title": p.title, "rationale": p.rationale, "evidence_refs": p.evidence_refs, "risk_level": p.risk_level,
        "certainty": p.certainty, "state": p.state, "decision_note": p.decision_note,
        "decided_at": p.decided_at.isoformat() if p.decided_at else None, "created_at": p.created_at.isoformat(),
        "result_revision_id": str(p.result_revision_id) if p.result_revision_id else None, "ai_generated": True,
    }
