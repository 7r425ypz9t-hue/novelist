"""«مسار الرواية»: where the novel stands in its working cycle, and the one next step worth taking.

Pure reading of project state (counts and timestamps only). Stages follow the life of a novel; each has a state
computed from data, never from a stored checklist, so it cannot drift from reality:

    done     — nothing is waiting here
    active   — something here deserves attention now
    todo     — not started yet
    optional — useful but not required (e.g. sources for a novel that cites none)

`next` is chosen by editorial priority, not by stage order: a high continuity conflict or a pending decision
outranks writing more words, and nothing pushes analysis on an almost empty draft.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import AgentRun, Character, Citation, Conflict, Document, Export, Node, Place, Project, Proposal, Revision

ANALYSIS_MIN_WORDS = 500


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    from datetime import UTC

    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def compute(db: Session, project: Project, perms: set[str]) -> dict[str, Any]:
    pid = project.id

    def count(model, *where) -> int:
        return db.scalar(select(func.count()).select_from(model).where(model.project_id == pid, *where)) or 0

    live_docs = list(db.scalars(select(Document).join(Node, Node.id == Document.node_id)
                                .where(Document.project_id == pid, Node.deleted_at.is_(None))))
    words = sum(d.word_count for d in live_docs)
    scenes = count(Node, Node.type == "scene", Node.deleted_at.is_(None))
    chapters = count(Node, Node.type == "chapter", Node.deleted_at.is_(None))
    empty_units = sum(1 for d in live_docs if d.word_count == 0)
    characters, places = count(Character), count(Place)
    pending = count(Proposal, Proposal.state == "pending")
    high = count(Conflict, Conflict.state == "open", Conflict.severity == "high")
    open_conf = count(Conflict, Conflict.state == "open")
    unverified = count(Citation, Citation.verification_state == "unverified")
    citations = count(Citation)
    last_edit = _aware(db.scalar(select(func.max(Revision.created_at)).where(Revision.project_id == pid)))
    last_check = _aware(db.scalar(select(func.max(AgentRun.finished_at)).where(
        AgentRun.project_id == pid, AgentRun.agent_id == "A00", AgentRun.status.in_(("succeeded", "partial")))))
    last_export = _aware(db.scalar(select(func.max(Export.created_at)).where(Export.project_id == pid,
                                                                             Export.status == "done")))
    goal = project.word_goal or 0
    progress = round(words / goal, 4) if goal else None
    can = perms.__contains__

    def stage(key, title, state, detail, label=None, to=None, needs=None):
        action = {"label": label, "to": to} if label and (needs is None or can(needs)) else None
        return {"key": key, "title": title, "state": state, "detail": detail, "action": action}

    base = f"/p/{pid}"
    stages = []
    found_missing = [x for x, ok in (("الجملة المحورية", bool(project.logline)), ("هدف الكلمات", bool(goal))) if not ok]
    stages.append(stage("foundation", "التأسيس", "done" if not found_missing else ("active" if words else "todo"),
                        "العنوان والجملة المحورية والهدف محدّدة" if not found_missing else "ينقص: " + "، ".join(found_missing),
                        "أكمل التأسيس", f"{base}/settings", "manage"))
    stages.append(stage("bible", "ذاكرة الرواية", "done" if characters else ("active" if words else "todo"),
                        f"الشخصيات: {characters} · الأماكن: {places}" if characters or places
                        else "لا شخصيات بعد — الاستمرارية تحتاجها لتعمل", "افتح الكتاب المرجعي", f"{base}/bible", "bible"))
    if not words:
        w_state, w_detail = "todo", "لم تبدأ الكتابة بعد"
    else:
        w_state = "done" if progress is not None and progress >= 1 and not empty_units else "active"
        w_detail = f"الكلمات: {words:,}" + (f" من {goal:,} ({round(progress * 100)}%)" if goal else "") + \
            f" · الفصول: {chapters} · المشاهد: {scenes}" + (f" · وحدات فارغة: {empty_units}" if empty_units else "")
    stages.append(stage("writing", "الكتابة", w_state, w_detail, "تابع الكتابة", f"{base}/write", "write"))
    if last_check is None and words < ANALYSIS_MIN_WORDS:
        a_state, a_detail = "todo", f"يُقترح بعد {ANALYSIS_MIN_WORDS} كلمة على الأقل"
    elif last_check is None:
        a_state, a_detail = "active", "لم يُجرَ فحص شامل بعد"
    elif last_edit and last_edit > last_check:
        a_state, a_detail = "active", "تغيّر النص منذ آخر فحص شامل"
    else:
        a_state, a_detail = "done", "آخر فحص شامل أحدث من آخر تعديل"
    stages.append(stage("analysis", "الفحص الشامل", a_state, a_detail, "شغّل الفحص الشامل", f"{base}/agents", "run_agents"))
    stages.append(stage("continuity", "الاستمرارية", "active" if high else "done",
                        f"تعارضات مفتوحة: {open_conf}، منها عالية: {high}" if open_conf else "لا تعارضات مفتوحة",
                        "راجع التعارضات", f"{base}/continuity"))
    stages.append(stage("decisions", "قرارات المقترحات", "active" if pending else "done",
                        f"بانتظار قرارك: {pending}" if pending else "لا مقترحات معلّقة",
                        "راجع المقترحات", f"{base}/proposals", "decide_proposals"))
    stages.append(stage("sources", "التوثيق", "active" if unverified else ("done" if citations else "optional"),
                        f"ادعاءات «غير متحقق»: {unverified}" if unverified
                        else ("كل الادعاءات موثّقة" if citations else "اختياري — للروايات التي تستند إلى وقائع"),
                        "افتح المصادر", f"{base}/sources", "sources"))
    blockers = [x for x, n in (("تعارضات عالية", high), ("مقترحات معلّقة", pending), ("وحدات فارغة", empty_units),
                               ("ادعاءات غير متحقق", unverified)) if n]
    if not words:
        p_state, p_detail = "todo", "لا نص بعد"
    elif blockers:
        p_state, p_detail = "todo", "قبل الإخراج: " + "، ".join(blockers)
    elif last_export and (last_edit is None or last_export >= last_edit):
        p_state, p_detail = "done", "آخر تصدير أحدث من آخر تعديل"
    else:
        p_state, p_detail = "active", "جاهزة للإخراج"
    stages.append(stage("publish", "الإخراج", p_state, p_detail, "صدّر الكتاب", f"{base}/publish", "export"))

    by = {s["key"]: s for s in stages}
    if not words:
        order = ["foundation", "writing"]
    else:
        order = ["continuity", "decisions", "analysis", "foundation", "bible", "sources", "writing", "publish"]
    nxt = next((by[k] for k in order if by[k]["state"] == "active" and by[k]["action"]), None)
    if nxt is None:
        nxt = next((s for s in stages if s["state"] in ("active", "todo") and s["action"]), None)
    why = {
        "continuity": "تعارض عالٍ قد يمسّ منطق الحكاية؛ حسمه أولاً يوفّر مراجعات لاحقة.",
        "decisions": "مقترحات تنتظر قرارك؛ لا يتغيّر نصك قبل أن تقبل أو ترفض.",
        "analysis": "النص تغيّر؛ الفحص الشامل يحدّث الاستمرارية والنقد في دفعة واحدة دون أن يمسّ النص.",
        "foundation": "الجملة المحورية والهدف يمنحان الفحص والقياس معياراً.",
        "bible": "الاستمرارية تبحث عن الشخصيات المسجّلة؛ سجّل الرئيسة منها.",
        "sources": "ادعاءات تاريخية بلا شاهد؛ اربطها بمصدر أو أبقِها «غير متحقق» عن وعي.",
        "writing": "الكتابة هي العمل؛ كل ما عداه يخدمها.",
        "publish": "لا عوائق قبل الإخراج؛ صدّر نسخة للقراءة أو للناشر.",
    }
    return {"stages": stages,
            "next": {**nxt, "why": why.get(nxt["key"], "")} if nxt else None,
            "done": sum(1 for s in stages if s["state"] == "done"), "total": len(stages)}
