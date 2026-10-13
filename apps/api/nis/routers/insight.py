"""Style fingerprint (LSIS) and the experimental NLQI rubric."""

import statistics
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..agents.registry import NLQI_DEFAULT_WEIGHTS, NLQI_LABELS
from ..db import get_db
from ..deps import Access, project_access
from ..errors import ProblemError, bad_request, not_found
from ..models import Assessment, Consent, Node, StyleProfile, utcnow
from ..schemas import AssessmentIn, StyleIn, WeightsIn
from ..security import sha256_hex
from ..services.style import ALLOWED_RIGHTS, LABELS, extract_features, merge_features

router = APIRouter(prefix="/v1/projects/{project_id}", tags=["insight"])


def style_out(s: StyleProfile) -> dict:
    return {"id": str(s.id), "name": s.name, "features": s.features, "sample_count": s.sample_count,
            "created_at": s.created_at.isoformat(), "labels": LABELS}


@router.get("/style-profiles")
def list_styles(acc: Access = Depends(project_access), db: Session = Depends(get_db)):
    rows = db.scalars(select(StyleProfile).where(StyleProfile.project_id == acc.project.id,
                                                 StyleProfile.deleted_at.is_(None)))
    return {"items": [style_out(s) for s in rows]}


@router.post("/style-profiles", status_code=201)
def create_style(body: StyleIn, acc: Access = Depends(project_access), db: Session = Depends(get_db)):
    acc.require("manage")
    if body.rights_basis not in ALLOWED_RIGHTS or not body.declaration:
        raise ProblemError(422, "عينة غير مأذون بها",
                           "لا تُضاف إلى البصمة إلا نصوص تملكها أو لديك إذن صريح بها، مع إقرار مكتوب.",
                           "/problems/unlicensed-sample")
    if body.imitate_author and body.imitate_author.strip():
        raise ProblemError(422, "تقليد مؤلف آخر غير مسموح",
                           "البصمة تحمي صوتك أنت؛ لا تُستخدم لمحاكاة مؤلف ثالث.", "/problems/imitation-refused")
    samples = [s for s in body.samples if s.strip()]
    if sum(len(s.split()) for s in samples) < 300:
        raise bad_request("تحتاج البصمة إلى 300 كلمة على الأقل من العينات.")
    consent = Consent(user_id=acc.user.id, project_id=acc.project.id, kind="style_sample",
                      scope={"rights_basis": body.rights_basis, "declaration": True})
    db.add(consent)
    db.flush()
    prof = StyleProfile(owner_id=acc.user.id, project_id=acc.project.id, name=body.name,
                        features=merge_features([extract_features(s) for s in samples]), consent_id=consent.id,
                        sample_count=len(samples), sample_hashes=[sha256_hex(s) for s in samples])
    db.add(prof)
    audit.record(db, "style.create", actor_id=acc.user.id, project_id=acc.project.id, object_type="style_profile",
                 meta={"samples": len(samples)})
    db.commit()
    return style_out(prof)


@router.delete("/style-profiles/{sid}", status_code=204)
def erase_style(sid: uuid.UUID, acc: Access = Depends(project_access), db: Session = Depends(get_db)):
    acc.require("manage")
    s = db.get(StyleProfile, sid)
    if not s or s.project_id != acc.project.id or s.deleted_at:
        raise not_found("البصمة")
    s.features, s.sample_hashes, s.deleted_at = {}, [], utcnow()
    if s.consent_id:
        c = db.get(Consent, s.consent_id)
        if c:
            c.revoked_at = utcnow()
    audit.record(db, "style.erase", actor_id=acc.user.id, project_id=acc.project.id, object_id=sid)
    db.commit()


# ───────────────────────── NLQI ─────────────────────────


def _weights(acc: Access) -> dict[str, float]:
    return {**NLQI_DEFAULT_WEIGHTS, **(acc.project.nlqi_weights or {})}


@router.put("/nlqi/weights")
def set_weights(body: WeightsIn, acc: Access = Depends(project_access), db: Session = Depends(get_db)):
    acc.require("manage")
    if set(body.weights) - set(NLQI_DEFAULT_WEIGHTS):
        raise bad_request("أبعاد غير معروفة في الأوزان.")
    w = {**NLQI_DEFAULT_WEIGHTS, **body.weights}
    if any(v < 0 for v in w.values()) or abs(sum(w.values()) - 100) > 1e-6:
        raise bad_request("مجموع الأوزان يجب أن يساوي 100 دون قيم سالبة.")
    acc.project.nlqi_weights = w
    db.commit()
    return {"weights": w}


@router.post("/nlqi/assessments", status_code=201)
def add_assessment(body: AssessmentIn, acc: Access = Depends(project_access), db: Session = Depends(get_db)):
    acc.require("comment")
    if set(body.scores) - set(NLQI_DEFAULT_WEIGHTS):
        raise bad_request("أبعاد غير معروفة.")
    if any(not 0 <= v <= 10 for v in body.scores.values()):
        raise bad_request("الدرجات بين 0 و10.")
    node_id = None
    if body.node_id:
        n = db.get(Node, uuid.UUID(body.node_id))
        if not n or n.project_id != acc.project.id:
            raise not_found("الوحدة")
        node_id = n.id
    a = Assessment(project_id=acc.project.id, node_id=node_id, rater_id=acc.user.id,
                   rater_label=body.rater_label or acc.user.display_name, scores=body.scores, notes=body.notes)
    db.add(a)
    db.commit()
    return {"id": str(a.id)}


@router.get("/nlqi")
def nlqi(acc: Access = Depends(project_access), db: Session = Depends(get_db)):
    """Aggregate human rubric scores. Shows inter-rater spread; never a machine verdict."""
    w = _weights(acc)
    rows = list(db.scalars(select(Assessment).where(Assessment.project_id == acc.project.id)
                           .order_by(Assessment.created_at)))
    per_rater = []
    dims: dict[str, list[float]] = {k: [] for k in w}
    for a in rows:
        covered = {k: v for k, v in a.scores.items() if k in w}
        wsum = sum(w[k] for k in covered) or 1
        idx = sum(w[k] * v / 10 for k, v in covered.items()) * 100 / wsum
        per_rater.append({"id": str(a.id), "rater": a.rater_label, "index": round(idx, 1), "scores": a.scores,
                          "notes": a.notes, "coverage": round(wsum / 100, 2), "created_at": a.created_at.isoformat()})
        for k, v in covered.items():
            dims[k].append(v)
    dimensions = []
    for k, vals in dims.items():
        dimensions.append({"key": k, "label": NLQI_LABELS[k], "weight": w[k],
                           "mean": round(statistics.mean(vals), 2) if vals else None,
                           "spread": round(statistics.pstdev(vals), 2) if len(vals) > 1 else None,
                           "raters": len(vals)})
    overall = round(statistics.mean(r["index"] for r in per_rater), 1) if per_rater else None
    return {"weights": w, "dimensions": dimensions, "assessments": per_rater, "index": overall,
            "disclaimer": "مؤشر NLQI تجريبي يجمع تقديرات بشرية بأوزان يحددها صاحب الرواية؛ ليس نتيجة علمية ولا "
                          "يستبدل المحكّمين. راجع التعليل والتباين بين المقيّمين."}
