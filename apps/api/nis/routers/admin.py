"""System administration. Operators see health, metrics and redacted audit — never manuscript content,
and titles of `private` projects are masked (SYSTEM_SPEC §2 «مسؤول النظام»)."""

import platform
import time
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .. import __version__, crypto
from ..agents.providers import get_provider
from ..config import get_settings
from ..db import get_db
from ..deps import admin_user
from ..errors import not_found
from ..models import (
    AgentRun,
    AuditEvent,
    Conflict,
    Document,
    Export,
    Project,
    Proposal,
    Revision,
    SourceChunk,
    SourceFile,
    User,
)
from ..storage import store

router = APIRouter(prefix="/v1/admin", tags=["admin"])
STARTED = time.time()


@router.get("/health")
def health(_: User = Depends(admin_user), db: Session = Depends(get_db)):
    t0 = time.perf_counter()
    db.execute(text("SELECT 1"))
    db_ms = round((time.perf_counter() - t0) * 1000, 2)
    s = get_settings()
    queued = db.scalar(select(func.count()).select_from(AgentRun).where(AgentRun.status.in_(("queued", "running"))))
    return {
        "status": "ok", "version": __version__, "uptime_s": int(time.time() - STARTED),
        "python": platform.python_version(),
        "database": {"ok": True, "latency_ms": db_ms, "engine": "sqlite" if s.is_sqlite else "postgresql"},
        "storage": {"ok": store().writable()},
        "encryption_at_rest": crypto.enabled(),
        "provider": get_provider().describe(),
        "worker": {"active_runs": queued or 0, "inline": s.runs_inline},
        "limits": {"rate_limit_per_minute": s.rate_limit_per_minute, "max_upload_mb": s.max_upload_mb,
                   "run_max_steps": s.run_max_steps, "run_token_budget": s.run_token_budget},
    }


@router.get("/metrics")
def metrics(_: User = Depends(admin_user), db: Session = Depends(get_db)):
    def count(model, *where):
        return db.scalar(select(func.count()).select_from(model).where(*where)) or 0

    runs_by_status = dict(db.execute(select(AgentRun.status, func.count()).group_by(AgentRun.status)).all())
    return {
        "users": count(User), "projects": count(Project), "documents": count(Document),
        "revisions": count(Revision), "words": int(db.scalar(select(func.coalesce(func.sum(Document.word_count), 0))) or 0),
        "sources": count(SourceFile), "chunks": count(SourceChunk),
        "flagged_chunks": int(db.scalar(select(func.coalesce(func.sum(SourceFile.flagged_chunks), 0))) or 0),
        "open_conflicts": count(Conflict, Conflict.state == "open"),
        "pending_proposals": count(Proposal, Proposal.state == "pending"),
        "exports": count(Export), "runs": runs_by_status,
        "tokens_used": int(db.scalar(select(func.coalesce(func.sum(AgentRun.tokens_used), 0))) or 0),
    }


@router.get("/agents")
def agent_operations(window: int = 300, stalled_minutes: int = 30, _: User = Depends(admin_user),
                     db: Session = Depends(get_db)):
    """Run health over the last `window` runs: per-skill outcome and duration, and runs that look stalled.
    Counts and timings only — no goals, findings or manuscript text."""
    from datetime import timedelta

    from ..agents.registry import SKILLS
    from ..models import utcnow

    rows = list(db.scalars(select(AgentRun).order_by(AgentRun.created_at.desc()).limit(min(max(window, 1), 2000))))
    per: dict[str, dict] = {}
    for r in rows:
        for st in list(r.steps or []) + list((r.output or {}).get("history") or []):  # earlier attempts count too
            k = st.get("skill", "?")
            d = per.setdefault(k, {"skill": k, "name": SKILLS.get(k, {}).get("name", ""), "done": 0, "failed": 0,
                                   "skipped": 0, "cancelled": 0, "durations": []})
            status = st.get("status")
            if status in ("done", "failed", "skipped", "cancelled"):
                d[status] += 1
            if isinstance(st.get("duration_ms"), int | float):
                d["durations"].append(st["duration_ms"])
    skills = []
    for d in per.values():
        ds = sorted(d.pop("durations"))
        n = d["done"] + d["failed"]
        skills.append({**d, "failure_rate": round(d["failed"] / n, 3) if n else 0.0,
                       "avg_ms": round(sum(ds) / len(ds)) if ds else None,
                       "p95_ms": ds[min(len(ds) - 1, int(len(ds) * 0.95))] if ds else None})
    skills.sort(key=lambda x: (-x["failure_rate"], -(x["p95_ms"] or 0)))
    cutoff = utcnow() - timedelta(minutes=stalled_minutes)
    stalled = [{"id": str(r.id), "agent_id": r.agent_id, "status": r.status,
                "since": (r.started_at or r.created_at).isoformat()}
               for r in rows if r.status in ("queued", "running")
               and (r.started_at or r.created_at).replace(tzinfo=cutoff.tzinfo) < cutoff]
    statuses: dict[str, int] = {}
    for r in rows:
        statuses[r.status] = statuses.get(r.status, 0) + 1
    finished = [r for r in rows if r.started_at and r.finished_at]
    return {"window": len(rows), "statuses": statuses, "skills": skills, "stalled": stalled,
            "avg_run_s": round(sum((r.finished_at - r.started_at).total_seconds() for r in finished) / len(finished), 2)
            if finished else None,
            "retried": sum(1 for r in rows if int((r.output or {}).get("attempts", 1)) > 1)}


@router.get("/users")
def users(_: User = Depends(admin_user), db: Session = Depends(get_db)):
    rows = db.execute(select(User, func.count(Project.id)).outerjoin(Project, Project.owner_id == User.id)
                      .group_by(User.id).order_by(User.created_at)).all()
    return {"items": [{"id": str(u.id), "email": u.email, "display_name": u.display_name, "is_admin": u.is_admin,
                       "is_active": u.is_active, "projects": n, "created_at": u.created_at.isoformat()}
                      for u, n in rows]}


@router.post("/users/{user_id}/active")
def set_active(user_id: uuid.UUID, active: bool, admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if not u or u.id == admin.id:
        raise not_found("المستخدم")
    u.is_active = active
    db.commit()
    return {"id": str(u.id), "is_active": u.is_active}


@router.get("/projects")
def projects(_: User = Depends(admin_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Project).order_by(Project.created_at.desc()))
    return {"items": [{"id": str(p.id), "title": p.title if p.privacy_mode == "shared" else "🔒 مشروع خاص",
                       "privacy_mode": p.privacy_mode, "status": p.status, "created_at": p.created_at.isoformat()}
                      for p in rows]}


@router.get("/audit")
def audit_log(limit: int = 100, action: str | None = None, _: User = Depends(admin_user),
              db: Session = Depends(get_db)):
    q = select(AuditEvent)
    if action:
        q = q.where(AuditEvent.action.like(f"{action}%"))
    rows = db.scalars(q.order_by(AuditEvent.at.desc()).limit(min(max(limit, 1), 500)))
    return {"items": [{"id": str(e.id), "at": e.at.isoformat(), "actor_id": str(e.actor_id) if e.actor_id else None,
                       "actor_type": e.actor_type, "project_id": str(e.project_id) if e.project_id else None,
                       "action": e.action, "object_type": e.object_type, "object_id": e.object_id,
                       "metadata": e.metadata_redacted} for e in rows]}
