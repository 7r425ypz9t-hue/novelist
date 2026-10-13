"""Agents, runs and proposals (Phase 4). Agents never accept their own proposals: decisions are human-only."""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..agents import orchestrator
from ..agents.providers import get_provider
from ..agents.registry import catalog
from ..db import get_db
from ..deps import Access, access_for, current_user, project_access
from ..errors import ProblemError, bad_request, not_found
from ..models import AgentRun, Proposal, User
from ..schemas import DecisionIn, RunIn
from ..services import proposals as svc

router = APIRouter(prefix="/v1", tags=["agents"])


@router.get("/agents/catalog")
def get_catalog(user: User = Depends(current_user)):
    return {**catalog(), "provider": get_provider().describe()}


@router.post("/agents/runs", status_code=202)
def start_run(body: RunIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        pid = uuid.UUID(body.project_id)
    except ValueError as e:
        raise bad_request("معرف المشروع غير صالح.") from e
    acc = access_for(db, user, pid).require("run_agents")
    run, created = orchestrator.create_run(
        db, project=acc.project, user_id=user.id, agent_id=body.agent_id, skills=body.skills, goal=body.goal,
        scope={"node_ids": body.node_ids} if body.node_ids else {}, idempotency_key=body.idempotency_key,
        use_model=body.use_model, acknowledge_external=body.acknowledge_external,
        confirm_high_risk=body.confirm_high_risk,
    )
    db.commit()
    if created:
        orchestrator.submit(run.id)
        db.refresh(run)
    return {**orchestrator.run_out(run), "deduplicated": not created}


def _run(db: Session, user: User, run_id: uuid.UUID) -> tuple[AgentRun, Access]:
    run = db.get(AgentRun, run_id)
    if not run:
        raise not_found("التشغيل")
    return run, access_for(db, user, run.project_id)


@router.get("/agents/runs/{run_id}")
def get_run(run_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    run, _ = _run(db, user, run_id)
    return orchestrator.run_out(run)


@router.post("/agents/runs/{run_id}/cancel")
def cancel_run(run_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    run, acc = _run(db, user, run_id)
    acc.require("run_agents")
    if run.status in ("succeeded", "failed", "cancelled"):
        return orchestrator.run_out(run)
    run.cancel_requested = True
    if run.status == "queued":
        run.status = "cancelled"
    audit.record(db, "agent_run.cancel", actor_id=user.id, project_id=run.project_id, object_id=run.id)
    db.commit()
    return orchestrator.run_out(run)


@router.get("/projects/{project_id}/runs")
def list_runs(limit: int = 30, acc: Access = Depends(project_access), db: Session = Depends(get_db)):
    rows = db.scalars(select(AgentRun).where(AgentRun.project_id == acc.project.id)
                      .order_by(AgentRun.created_at.desc()).limit(min(max(limit, 1), 100)))
    return {"items": [orchestrator.run_out(r, full=False) for r in rows]}


# ───────────────────────── proposals ─────────────────────────


@router.get("/projects/{project_id}/proposals")
def list_proposals(state: str | None = "pending", document_id: uuid.UUID | None = None, limit: int = 200,
                   acc: Access = Depends(project_access), db: Session = Depends(get_db)):
    q = select(Proposal).where(Proposal.project_id == acc.project.id)
    if state and state != "all":
        q = q.where(Proposal.state == state)
    if document_id:
        q = q.where(Proposal.document_id == document_id)
    rows = db.scalars(q.order_by(Proposal.created_at.desc()).limit(min(max(limit, 1), 500)))
    return {"items": [svc.proposal_out(p) for p in rows]}


def _proposal(db: Session, user: User, pid: uuid.UUID) -> tuple[Proposal, Access]:
    p = db.get(Proposal, pid)
    if not p:
        raise not_found("المقترح")
    return p, access_for(db, user, p.project_id)


@router.get("/proposals/{proposal_id}")
def get_proposal(proposal_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p, _ = _proposal(db, user, proposal_id)
    return {**svc.proposal_out(p), "preview": svc.preview(db, p)}


@router.post("/proposals/{proposal_id}/accept")
def accept(proposal_id: uuid.UUID, body: DecisionIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p, acc = _proposal(db, user, proposal_id)
    acc.require("decide_proposals")
    if p.kind == "fact" and body.as_canon:
        acc.require("approve_canon")
    try:
        result = svc.accept(db, p, user.id, edited_ops=body.edited_ops, allow_rebase=body.allow_rebase,
                            as_canon=body.as_canon, note=body.note)
    except ProblemError:
        if p.state == "stale":
            db.commit()  # persist the stale marker, nothing else
        else:
            db.rollback()
        raise
    db.commit()
    return {**svc.proposal_out(p), "result": result}


@router.post("/proposals/{proposal_id}/reject")
def reject(proposal_id: uuid.UUID, body: DecisionIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p, acc = _proposal(db, user, proposal_id)
    acc.require("decide_proposals")
    svc.reject(db, p, user.id, body.note)
    db.commit()
    return svc.proposal_out(p)
