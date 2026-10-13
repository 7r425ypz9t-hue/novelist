"""A00 orchestrator: deterministic planning, checkpointed steps, cancellation, idempotent retries (§11).

Runs are persisted; each finished step is checkpointed in `run.steps` so a restarted worker resumes without
re-executing completed steps. Proposal fingerprints make retries side-effect free (AT20).
"""

from __future__ import annotations

import logging
import threading
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..config import get_settings
from ..db import SessionLocal
from ..errors import ProblemError, bad_request
from ..models import AgentRun, Consent, Document, Project, utcnow
from ..security import sha256_hex
from . import skills as skills_mod
from .context import ToolContext
from .providers import Provider, estimate_cost, get_provider
from .registry import AGENTS, PIPELINE, SKILLS

log = logging.getLogger("nis.orchestrator")
_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="nis-run")
_lock = threading.Lock()


def plan(agent_id: str, requested: list[str] | None) -> list[tuple[str, str]]:
    """Return ordered (agent, skill) steps."""
    if agent_id not in AGENTS:
        raise bad_request("وكيل غير معروف.")
    if agent_id == "A00":
        steps: list[tuple[str, str]] = []
        for stage in PIPELINE:
            for a in stage:
                for s in AGENTS[a]["skills"]:
                    if requested and s not in requested:
                        continue
                    if (a, s) not in steps and not any(x[1] == s and s != "SK15" for x in steps):
                        steps.append((a, s))
        return steps
    allowed = AGENTS[agent_id]["skills"]
    chosen = [s for s in (requested or allowed) if s in allowed]
    if not chosen:
        raise bad_request("المهارات المطلوبة ليست ضمن اختصاص هذا الوكيل.")
    return [(agent_id, s) for s in chosen]


def risk_of(steps: list[tuple[str, str]], uses_external: bool) -> str:
    if uses_external:
        return "HIGH"
    order = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
    return max((SKILLS[s]["risk"] for _, s in steps), key=lambda r: order[r], default="LOW")


def has_external_consent(db: Session, user_id: uuid.UUID, project_id: uuid.UUID) -> bool:
    return db.scalar(select(Consent.id).where(Consent.user_id == user_id, Consent.project_id == project_id,
                                              Consent.kind == "external_ai", Consent.revoked_at.is_(None))) is not None


def create_run(db: Session, *, project: Project, user_id: uuid.UUID, agent_id: str, skills: list[str] | None,
               goal: str, scope: dict[str, Any], idempotency_key: str, use_model: bool,
               acknowledge_external: bool, confirm_high_risk: bool) -> tuple[AgentRun, bool]:
    existing = db.scalar(select(AgentRun).where(AgentRun.project_id == project.id,
                                                AgentRun.idempotency_key == idempotency_key))
    if existing:
        return existing, False
    if not project.ai_enabled:
        raise ProblemError(409, "الوكلاء معطّلون", "عُطّلت الميزات التحليلية والتوليدية لهذا المشروع من إعداداته.",
                           "/problems/agents-disabled")
    steps = plan(agent_id, skills)
    provider = get_provider()
    allow_model = bool(use_model and provider.available())
    if allow_model and provider.external:
        if not has_external_consent(db, user_id, project.id):
            raise ProblemError(
                403, "موافقة نقل البيانات مطلوبة",
                "تشغيل نموذج خارجي يرسل مقاطع من المخطوط إلى " + provider.describe()["destination"]
                + ". امنح موافقة المشروع من الإعدادات أولاً.", "/problems/consent-required",
                destination=provider.describe()["destination"])
        if not acknowledge_external:
            raise ProblemError(428, "تأكيد الإرسال الخارجي مطلوب",
                               "أكّد أنك تعلم بوجهة البيانات قبل هذا التشغيل.", "/problems/acknowledge-external",
                               destination=provider.describe()["destination"])
    risk = risk_of(steps, allow_model and provider.external)
    if risk == "HIGH" and not confirm_high_risk:
        raise ProblemError(428, "تأكيد منفصل مطلوب", "هذا التشغيل عالي المخاطرة ويحتاج تأكيداً منفصلاً.",
                           "/problems/confirm-high-risk")
    docs = db.scalars(select(Document).where(Document.project_id == project.id))
    base = {str(d.id): str(d.current_revision_id) for d in docs}
    run = AgentRun(
        project_id=project.id, agent_id=agent_id, skills=[s for _, s in steps], goal=goal[:4000], scope=scope,
        base_revisions=base, provider=provider.name if allow_model else "disabled",
        model_id=provider.describe().get("model", "deterministic") if allow_model else "deterministic",
        risk_level=risk, idempotency_key=idempotency_key,
        input_hash=sha256_hex(f"{agent_id}|{sorted(base.items())}|{goal}|{scope}"),
        steps=[{"agent": a, "skill": s, "status": "pending"} for a, s in steps],
        output={"allow_model": allow_model}, requested_by=user_id,
    )
    db.add(run)
    db.flush()
    audit.record(db, "agent_run.create", actor_id=user_id, project_id=project.id, object_type="agent_run",
                 object_id=run.id, meta={"agent": agent_id, "skills": ",".join(run.skills), "risk": risk,
                                         "provider": run.provider})
    return run, True


def submit(run_id: uuid.UUID) -> None:
    if get_settings().runs_inline:
        execute(run_id)
    else:
        _pool.submit(execute, run_id)


def execute(run_id: uuid.UUID) -> None:
    db = SessionLocal()
    try:
        _execute(db, run_id)
    except Exception:  # noqa: BLE001 - recorded on the run
        db.rollback()
        run = db.get(AgentRun, run_id)
        if run:
            run.status, run.error, run.finished_at = "failed", traceback.format_exc(limit=3)[-2000:], utcnow()
            db.commit()
    finally:
        db.close()


def _execute(db: Session, run_id: uuid.UUID) -> None:
    with _lock:
        run = db.get(AgentRun, run_id)
        if not run or run.status in ("succeeded", "failed", "cancelled"):
            return
        run.status = "running"
        run.started_at = run.started_at or utcnow()
        db.commit()
    s = get_settings()
    provider: Provider = get_provider() if run.provider != "disabled" else Provider()
    opts = {"allow_model": bool((run.output or {}).get("allow_model"))}
    results: dict[str, Any] = dict((run.output or {}).get("results") or {})
    for i, step in enumerate(list(run.steps)):
        if step.get("status") == "done":
            continue  # checkpoint: resume after restart without repeating work
        db.refresh(run)
        if run.cancel_requested:
            run.status, run.finished_at = "cancelled", utcnow()
            _mark(run, i, "cancelled")
            db.commit()
            return
        if i >= s.run_max_steps:
            _mark(run, i, "skipped", note="تجاوز الحد الأقصى للخطوات")
            continue
        if run.tokens_used >= s.run_token_budget:
            opts["allow_model"] = False
            _mark(run, i, step.get("status", "pending"), note="نفدت ميزانية الرموز — يُكمل حتمياً")
        ctx = ToolContext(db, run.project_id, run.id, step["agent"], (run.scope or {}).get("node_ids"))
        fn = skills_mod.REGISTRY.get(step["skill"])
        started = utcnow()
        if fn is None:
            _mark(run, i, "skipped", note="مهارة غير منفذة")
            continue
        res = fn(ctx, provider, opts)
        run.tokens_used += res.tokens
        results[f"{step['agent']}:{step['skill']}"] = res.as_dict()
        _mark(run, i, "done", started=started.isoformat(), finished=utcnow().isoformat(),
              summary=res.summary, findings=len(res.findings), proposals=res.proposals_created)
        out = dict(run.output or {})
        out["results"] = results
        run.output = out
        db.commit()
    cost = estimate_cost(run.tokens_used, 0) if run.tokens_used else 0.0
    run.cost_estimate_usd = cost or 0.0
    out = dict(run.output or {})
    out["report"] = editorial_report(results)
    out["cost_note"] = "" if cost is not None else "التكلفة غير محسوبة: لم يحدد المشغل أسعار المزود."
    run.output = out
    run.status, run.finished_at = "succeeded", utcnow()
    audit.record(db, "agent_run.finish", actor_id=None, actor_type="agent", project_id=run.project_id,
                 object_type="agent_run", object_id=run.id,
                 meta={"status": run.status, "tokens": run.tokens_used,
                       "proposals": sum(int(x.get("proposals", 0) or 0) for x in run.steps)})
    db.commit()


def _mark(run: AgentRun, i: int, status: str, **extra: Any) -> None:
    steps = [dict(x) for x in run.steps]
    steps[i].update({"status": status, **{k: v for k, v in extra.items() if v is not None}})
    run.steps = steps


AREAS = ["بنية", "شخصيات", "لغة", "حوار", "إيقاع", "مصداقية", "راوٍ", "زمن", "عالم", "رموز", "أسلوب", "عمق",
         "تأثير", "استمرارية", "أصالة", "حقوق", "نشر"]


def editorial_report(results: dict[str, Any]) -> dict[str, Any]:
    """FR16: a separate report grouped by area, keeping objective findings apart from taste."""
    sections: dict[str, dict[str, list]] = {}
    for key, res in results.items():
        for f in res.get("findings", []):
            area = f.get("area") or "عام"
            bucket = sections.setdefault(area, {"objective": [], "taste": []})
            bucket["taste" if f.get("kind") == "taste" else "objective"].append({**f, "source": key})
    ordered = {a: sections[a] for a in AREAS if a in sections}
    ordered.update({a: v for a, v in sections.items() if a not in ordered})
    return {"sections": ordered,
            "disclaimer": "تقرير مساعد: الملاحظات «الموضوعية» قابلة للتحقق من النص، و«الذوقية» اقتراحات نقدية "
                          "لا أحكام. لم يُعدَّل أي نص."}


def resume_pending() -> int:
    """Called at startup: re-submit runs left queued/running by a previous process."""
    db = SessionLocal()
    try:
        ids = list(db.scalars(select(AgentRun.id).where(AgentRun.status.in_(("queued", "running")))))
    finally:
        db.close()
    for rid in ids:
        submit(rid)
    return len(ids)


def run_out(r: AgentRun, full: bool = True) -> dict[str, Any]:
    d = {
        "id": str(r.id), "project_id": str(r.project_id), "agent_id": r.agent_id,
        "agent_name": AGENTS.get(r.agent_id, {}).get("name", ""), "skills": r.skills, "goal": r.goal,
        "status": r.status, "risk_level": r.risk_level, "provider": r.provider, "model_id": r.model_id,
        "tokens_used": r.tokens_used, "cost_estimate_usd": r.cost_estimate_usd, "steps": r.steps,
        "idempotency_key": r.idempotency_key, "created_at": r.created_at.isoformat(),
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "finished_at": r.finished_at.isoformat() if r.finished_at else None, "error": r.error[-400:] if r.error else "",
        "cancel_requested": r.cancel_requested,
    }
    if full:
        d["output"] = r.output
    return d
