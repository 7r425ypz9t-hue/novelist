"""Continuity board + source library, retrieval and citations."""

import uuid

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..config import get_settings
from ..db import get_db
from ..deps import Access, project_access
from ..errors import ProblemError, bad_request, not_found
from ..models import Citation, Conflict, Document, SourceChunk, SourceFile, utcnow
from ..schemas import CitationIn, QueryIn, ResolveIn, SourcePatch
from ..security import sha256_hex
from ..services import research
from ..services.continuity import conflict_out, run_scan
from ..storage import store

router = APIRouter(prefix="/v1/projects/{project_id}", tags=["continuity", "research"])


# ───────────────────────── continuity ─────────────────────────


@router.post("/continuity/scan")
def scan(acc: Access = Depends(project_access), db: Session = Depends(get_db)):
    acc.require("bible")
    stats = run_scan(db, acc.project.id)
    audit.record(db, "continuity.scan", actor_id=acc.user.id, project_id=acc.project.id, meta=stats)
    db.commit()
    return stats


@router.get("/conflicts")
def list_conflicts(state: str | None = "open", acc: Access = Depends(project_access), db: Session = Depends(get_db)):
    q = select(Conflict).where(Conflict.project_id == acc.project.id)
    if state and state != "all":
        q = q.where(Conflict.state == state)
    order = {"high": 0, "medium": 1, "low": 2}
    rows = sorted(db.scalars(q), key=lambda c: (order.get(c.severity, 3), c.created_at))
    return {"items": [conflict_out(c) for c in rows]}


@router.post("/conflicts/{cid}/resolve")
def resolve(cid: uuid.UUID, body: ResolveIn, acc: Access = Depends(project_access), db: Session = Depends(get_db)):
    acc.require("bible")
    c = db.get(Conflict, cid)
    if not c or c.project_id != acc.project.id:
        raise not_found("التعارض")
    if body.action == "waive" and len(body.note.strip()) < 3:
        raise bad_request("الإعفاء يتطلب سبباً مكتوباً (مثل: راوٍ غير موثوق عمداً).")
    c.state = {"resolve": "resolved", "waive": "waived", "dismiss": "dismissed", "reopen": "open"}[body.action]
    c.resolution_note, c.resolved_by, c.resolved_at = body.note, acc.user.id, utcnow() if body.action != "reopen" else None
    audit.record(db, f"conflict.{body.action}", actor_id=acc.user.id, project_id=acc.project.id, object_id=cid)
    db.commit()
    return conflict_out(c)


# ───────────────────────── sources ─────────────────────────


@router.get("/sources")
def list_sources(acc: Access = Depends(project_access), db: Session = Depends(get_db)):
    rows = db.scalars(select(SourceFile).where(SourceFile.project_id == acc.project.id).order_by(SourceFile.created_at.desc()))
    return {"items": [research.source_out(s) for s in rows]}


@router.post("/sources", status_code=201)
async def upload_source(
    file: UploadFile = File(...), license_state: str = Form(...), usage_consent: bool = Form(False),
    title: str = Form(""), author: str = Form(""), acc: Access = Depends(project_access), db: Session = Depends(get_db),
):
    acc.require("sources")
    if license_state not in research.LICENSE_STATES:
        raise bad_request("حالة الترخيص غير صالحة.")
    data = await file.read()
    if len(data) > get_settings().max_upload_mb * 1024 * 1024:
        raise ProblemError(413, "الملف كبير", "تجاوز الحد المسموح للرفع.", "/problems/too-large")
    if not data:
        raise bad_request("الملف فارغ.")
    ftype = research.detect_type(file.filename or "", data)
    sid = uuid.uuid4()
    key = f"projects/{acc.project.id}/sources/{sid}.{ftype}"
    store().put(key, data)
    src = SourceFile(id=sid, project_id=acc.project.id, filename=(file.filename or "")[:300], file_type=ftype,
                     size=len(data), sha256=sha256_hex(data), object_key=key, title=title or (file.filename or ""),
                     author=author, license_state=license_state, usage_consent=usage_consent,
                     uploaded_by=acc.user.id)
    db.add(src)
    db.flush()
    research.ingest(db, src, data)
    audit.record(db, "source.upload", actor_id=acc.user.id, project_id=acc.project.id, object_type="source",
                 object_id=sid, meta={"type": ftype, "license": license_state, "flagged": src.flagged_chunks})
    db.commit()
    return research.source_out(src)


@router.patch("/sources/{sid}")
def patch_source(sid: uuid.UUID, body: SourcePatch, acc: Access = Depends(project_access), db: Session = Depends(get_db)):
    acc.require("sources")
    s = db.get(SourceFile, sid)
    if not s or s.project_id != acc.project.id:
        raise not_found("المصدر")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(s, k, v)
    db.commit()
    return research.source_out(s)


@router.get("/sources/{sid}/chunks")
def source_chunks(sid: uuid.UUID, acc: Access = Depends(project_access), db: Session = Depends(get_db)):
    s = db.get(SourceFile, sid)
    if not s or s.project_id != acc.project.id:
        raise not_found("المصدر")
    rows = db.scalars(select(SourceChunk).where(SourceChunk.source_file_id == sid).order_by(SourceChunk.ordinal))
    return {"source": research.source_out(s),
            "items": [{"id": str(c.id), "locator": c.locator, "page": c.page, "content": c.content,
                       "flags": c.flags} for c in rows]}


@router.get("/sources/{sid}/citations")
def source_citations(sid: uuid.UUID, acc: Access = Depends(project_access), db: Session = Depends(get_db)):
    s = db.get(SourceFile, sid)
    if not s or s.project_id != acc.project.id:
        raise not_found("المصدر")
    rows = db.execute(select(Citation, SourceChunk).join(SourceChunk, SourceChunk.id == Citation.source_chunk_id)
                      .where(SourceChunk.source_file_id == sid)).all()
    return {"items": [_cit_out(c, ch) for c, ch in rows]}


@router.delete("/sources/{sid}", status_code=204)
def delete_source(sid: uuid.UUID, acc: Access = Depends(project_access), db: Session = Depends(get_db)):
    acc.require("sources")
    s = db.get(SourceFile, sid)
    if not s or s.project_id != acc.project.id:
        raise not_found("المصدر")
    # citations that pointed into this source fall back to `unverified` — never silently "verified"
    chunk_ids = list(db.scalars(select(SourceChunk.id).where(SourceChunk.source_file_id == sid)))
    for c in db.scalars(select(Citation).where(Citation.source_chunk_id.in_(chunk_ids))):
        c.source_chunk_id, c.verification_state = None, "unverified"
        c.note = (c.note + " | حُذف المصدر المرتبط").strip(" |")
    research.delete_source(db, s)
    audit.record(db, "source.delete", actor_id=acc.user.id, project_id=acc.project.id, object_id=sid)
    db.commit()


@router.post("/research/query")
def query(body: QueryIn, acc: Access = Depends(project_access), db: Session = Depends(get_db)):
    res = research.search(db, acc.project.id, body.question, k=body.k)
    audit.record(db, "research.query", actor_id=acc.user.id, project_id=acc.project.id,
                 meta={"hits": len(res["hits"]), "verdict": res["verdict"]})
    db.commit()
    return res


# ───────────────────────── citations ─────────────────────────


def _cit_out(c: Citation, ch: SourceChunk | None = None) -> dict:
    return {"id": str(c.id), "claim_text": c.claim_text, "document_id": str(c.document_id) if c.document_id else None,
            "span": c.span, "source_chunk_id": str(c.source_chunk_id) if c.source_chunk_id else None,
            "verification_state": c.verification_state, "note": c.note,
            "locator": ch.locator if ch else None, "excerpt": ch.content[:400] if ch else None}


@router.get("/citations")
def list_citations(acc: Access = Depends(project_access), db: Session = Depends(get_db)):
    rows = db.execute(select(Citation, SourceChunk).outerjoin(SourceChunk, SourceChunk.id == Citation.source_chunk_id)
                      .where(Citation.project_id == acc.project.id).order_by(Citation.created_at.desc())).all()
    return {"items": [_cit_out(c, ch) for c, ch in rows]}


@router.post("/citations", status_code=201)
def add_citation(body: CitationIn, acc: Access = Depends(project_access), db: Session = Depends(get_db)):
    acc.require("write")
    chunk = None
    if body.source_chunk_id:
        chunk = db.get(SourceChunk, uuid.UUID(body.source_chunk_id))
        if not chunk or chunk.project_id != acc.project.id:
            raise not_found("المقطع")
    doc_id = None
    if body.document_id:
        d = db.get(Document, uuid.UUID(body.document_id))
        if not d or d.project_id != acc.project.id:
            raise not_found("المستند")
        doc_id = d.id
    c = Citation(project_id=acc.project.id, claim_text=body.claim_text, document_id=doc_id, span=body.span,
                 source_chunk_id=chunk.id if chunk else None,
                 verification_state="verified" if chunk else "unverified", note=body.note, created_by=acc.user.id)
    db.add(c)
    db.commit()
    return _cit_out(c, chunk)


@router.delete("/citations/{cid}", status_code=204)
def delete_citation(cid: uuid.UUID, acc: Access = Depends(project_access), db: Session = Depends(get_db)):
    acc.require("write")
    c = db.get(Citation, cid)
    if not c or c.project_id != acc.project.id:
        raise not_found("الاستشهاد")
    db.delete(c)
    db.commit()
