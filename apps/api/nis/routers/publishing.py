"""Exports (DOCX/PDF/EPUB/MD), full data export, archive restore, project deletion."""

import re
import uuid

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..config import get_settings
from ..db import get_db
from ..deps import Access, access_for, current_user, project_access
from ..errors import ProblemError, bad_request, not_found
from ..models import Export, Manuscript, User
from ..schemas import DeleteProjectIn, ExportIn
from ..security import sha256_hex
from ..services import portability
from ..services.exports import MEDIA, RENDERERS, compile_book
from ..storage import store

router = APIRouter(prefix="/v1", tags=["publishing"])


def _safe_name(title: str) -> str:
    return re.sub(r"[^\w؀-ۿ\- ]+", "", title).strip().replace(" ", "_")[:80] or "manuscript"


def export_out(e: Export) -> dict:
    return {"id": str(e.id), "format": e.format, "status": e.status, "filename": e.filename, "size": e.size,
            "sha256": e.sha256, "error": e.error, "created_at": e.created_at.isoformat()}


@router.post("/projects/{project_id}/exports", status_code=201)
def create_export(body: ExportIn, acc: Access = Depends(project_access), db: Session = Depends(get_db)):
    acc.require("export")
    ms = None
    if body.manuscript_id:
        ms = db.get(Manuscript, uuid.UUID(body.manuscript_id))
        if not ms or ms.project_id != acc.project.id:
            raise not_found("المخطوط")
    book = compile_book(db, acc.project, ms)
    e = Export(project_id=acc.project.id, format=body.format, requested_by=acc.user.id, status="running")
    db.add(e)
    db.flush()
    try:
        data = RENDERERS[body.format](book)
    except Exception as ex:  # noqa: BLE001 - reported to the user
        e.status, e.error = "failed", f"{type(ex).__name__}: {str(ex)[:300]}"
        db.commit()
        raise ProblemError(500, "فشل التصدير", e.error, "/problems/export-failed") from ex
    key = f"projects/{acc.project.id}/exports/{e.id}.{body.format}"
    store().put(key, data)
    e.object_key, e.size, e.sha256, e.status = key, len(data), sha256_hex(data), "done"
    e.filename = f"{_safe_name(book.title)}.{body.format}"
    audit.record(db, "export.create", actor_id=acc.user.id, project_id=acc.project.id, object_type="export",
                 object_id=e.id, meta={"format": body.format, "size": len(data)})
    db.commit()
    return export_out(e)


@router.get("/projects/{project_id}/exports")
def list_exports(acc: Access = Depends(project_access), db: Session = Depends(get_db)):
    rows = db.scalars(select(Export).where(Export.project_id == acc.project.id).order_by(Export.created_at.desc()).limit(50))
    return {"items": [export_out(e) for e in rows]}


@router.get("/exports/{export_id}")
def get_export(export_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    e = db.get(Export, export_id)
    if not e:
        raise not_found("التصدير")
    access_for(db, user, e.project_id).require("export")
    return export_out(e)


@router.get("/exports/{export_id}/download")
def download_export(export_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    e = db.get(Export, export_id)
    if not e or e.status != "done":
        raise not_found("التصدير")
    access_for(db, user, e.project_id).require("export")
    data = store().get(e.object_key)
    from urllib.parse import quote

    return Response(data, media_type=MEDIA.get(e.format, "application/octet-stream"),
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(e.filename)}",
                             "X-Content-SHA256": e.sha256})


@router.post("/projects/{project_id}/data-export")
def data_export(acc: Access = Depends(project_access), db: Session = Depends(get_db)):
    acc.require("manage")
    data = portability.export_archive(db, acc.project)
    audit.record(db, "project.data_export", actor_id=acc.user.id, project_id=acc.project.id, meta={"size": len(data)})
    db.commit()
    from urllib.parse import quote

    name = f"{_safe_name(acc.project.title)}-archive.zip"
    return Response(data, media_type="application/zip",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}",
                             "X-Content-SHA256": sha256_hex(data)})


@router.post("/projects/import", status_code=201)
async def import_project(file: UploadFile = File(...), user: User = Depends(current_user), db: Session = Depends(get_db)):
    raw = await file.read()
    if len(raw) > get_settings().max_upload_mb * 4 * 1024 * 1024:
        raise ProblemError(413, "الأرشيف كبير", "تجاوز الحد المسموح.", "/problems/too-large")
    project = portability.import_archive(db, raw, user.id)
    audit.record(db, "project.restore", actor_id=user.id, project_id=project.id, object_type="project",
                 object_id=project.id)
    db.commit()
    return {"id": str(project.id), "title": project.title}


@router.post("/projects/{project_id}/data-merge")
async def merge_project(file: UploadFile = File(...), acc: Access = Depends(project_access), db: Session = Depends(get_db)):
    """Update this project from an archive of the same novel exported on the writer's other computer."""
    acc.require("manage")
    raw = await file.read()
    if len(raw) > get_settings().max_upload_mb * 4 * 1024 * 1024:
        raise ProblemError(413, "الأرشيف كبير", "تجاوز الحد المسموح.", "/problems/too-large")
    report = portability.merge_archive(db, raw, acc.project, acc.user.id)
    d = report["documents"]
    audit.record(db, "project.data_merge", actor_id=acc.user.id, project_id=acc.project.id,
                 meta={"fast_forward": len(d["fast_forward"]), "diverged": len(d["diverged"]), "new": len(d["new"]),
                       "added": sum(report["added"].values())})
    db.commit()
    return report


@router.delete("/projects/{project_id}")
def delete_project(body: DeleteProjectIn, acc: Access = Depends(project_access), db: Session = Depends(get_db)):
    """Hard delete after typed confirmation. Derived data (chunks, exports, files) is deleted with it."""
    acc.require("delete")
    if body.confirm_title.strip() != acc.project.title.strip():
        raise bad_request("اكتب عنوان المشروع حرفياً لتأكيد الحذف النهائي.")
    pid = acc.project.id
    db.delete(acc.project)
    audit.record(db, "project.delete", actor_id=acc.user.id, project_id=pid, object_type="project", object_id=pid)
    db.commit()
    store().delete_prefix(f"projects/{pid}")
    return {"deleted": str(pid),
            "retention": "حُذفت البيانات من قاعدة البيانات والتخزين فوراً؛ قد تبقى في النسخ الاحتياطية حتى انتهاء "
                         "دورة الاحتفاظ المعلنة في دليل التشغيل."}
