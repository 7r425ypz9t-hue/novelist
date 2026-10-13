"""Story Bible: characters, places, events, relations, causal facts, timeline and knowledge graph."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..deps import Access, project_access
from ..errors import bad_request, not_found
from ..models import CanonFact, Character, EntityEdge, Event, Node, Place, utcnow
from ..schemas import CharacterIn, CharacterPatch, EdgeIn, EventIn, EventPatch, FactIn, PlaceIn, PlacePatch
from ..services.manuscript import labels, ordered_nodes

router = APIRouter(prefix="/v1/projects/{project_id}", tags=["story-bible"])


def _id(v: Any) -> str | None:
    return str(v) if v is not None else None


def char_out(c: Character) -> dict:
    return {"id": str(c.id), "canonical_name": c.canonical_name, "aliases": c.aliases, "profile": c.profile,
            "status": c.status}


def place_out(p: Place) -> dict:
    return {"id": str(p.id), "name": p.name, "aliases": p.aliases, "profile": p.profile, "lat": p.lat, "lon": p.lon}


def event_out(e: Event) -> dict:
    return {"id": str(e.id), "title": e.title, "summary": e.summary, "story_time_start": e.story_time_start,
            "story_time_end": e.story_time_end, "time_label": e.time_label, "uncertainty": e.uncertainty,
            "probability": e.probability, "narration_order": e.narration_order, "node_id": _id(e.node_id),
            "place_id": _id(e.place_id), "participant_ids": e.participant_ids, "kind": e.kind}


def fact_out(f: CanonFact) -> dict:
    return {"id": str(f.id), "subject_type": f.subject_type, "subject_id": _id(f.subject_id),
            "subject_label": f.subject_label, "predicate": f.predicate, "object": f.object, "statement": f.statement,
            "epistemic_status": f.epistemic_status, "valid_from": f.valid_from, "valid_to": f.valid_to,
            "source_refs": f.source_refs, "confidence": f.confidence, "origin": f.origin,
            "approved_by": _id(f.approved_by), "approved_at": f.approved_at.isoformat() if f.approved_at else None}


def _own(db: Session, model: Any, oid: uuid.UUID, acc: Access, what: str) -> Any:
    obj = db.get(model, oid)
    if not obj or obj.project_id != acc.project.id:
        raise not_found(what)
    return obj


def _check_ref(db: Session, model: Any, raw: str | None, acc: Access, what: str) -> uuid.UUID | None:
    if not raw:
        return None
    try:
        oid = uuid.UUID(raw)
    except ValueError as e:
        raise bad_request(f"معرف {what} غير صالح.") from e
    _own(db, model, oid, acc, what)
    return oid


# ── characters
@router.get("/characters")
def list_characters(acc: Access = Depends(project_access), db: Session = Depends(get_db)):
    rows = db.scalars(select(Character).where(Character.project_id == acc.project.id).order_by(Character.canonical_name))
    return {"items": [char_out(c) for c in rows]}


@router.post("/characters", status_code=201)
def add_character(body: CharacterIn, acc: Access = Depends(project_access), db: Session = Depends(get_db)):
    acc.require("bible")
    c = Character(project_id=acc.project.id, **body.model_dump())
    db.add(c)
    audit.record(db, "character.create", actor_id=acc.user.id, project_id=acc.project.id, object_type="character")
    db.commit()
    return char_out(c)


@router.patch("/characters/{cid}")
def patch_character(cid: uuid.UUID, body: CharacterPatch, acc: Access = Depends(project_access),
                    db: Session = Depends(get_db)):
    acc.require("bible")
    c = _own(db, Character, cid, acc, "الشخصية")
    data = body.model_dump(exclude_unset=True)
    if "profile" in data:
        prof = dict(c.profile or {})
        prof.update(data.pop("profile") or {})
        c.profile = {k: v for k, v in prof.items() if v not in (None, "")}
    for k, v in data.items():
        setattr(c, k, v)
    db.commit()
    return char_out(c)


@router.delete("/characters/{cid}", status_code=204)
def delete_character(cid: uuid.UUID, acc: Access = Depends(project_access), db: Session = Depends(get_db)):
    acc.require("bible")
    db.delete(_own(db, Character, cid, acc, "الشخصية"))
    audit.record(db, "character.delete", actor_id=acc.user.id, project_id=acc.project.id, object_id=cid)
    db.commit()


# ── places
@router.get("/places")
def list_places(acc: Access = Depends(project_access), db: Session = Depends(get_db)):
    return {"items": [place_out(p) for p in db.scalars(select(Place).where(Place.project_id == acc.project.id))]}


@router.post("/places", status_code=201)
def add_place(body: PlaceIn, acc: Access = Depends(project_access), db: Session = Depends(get_db)):
    acc.require("bible")
    p = Place(project_id=acc.project.id, **body.model_dump())
    db.add(p)
    db.commit()
    return place_out(p)


@router.patch("/places/{pid}")
def patch_place(pid: uuid.UUID, body: PlacePatch, acc: Access = Depends(project_access), db: Session = Depends(get_db)):
    acc.require("bible")
    p = _own(db, Place, pid, acc, "المكان")
    data = body.model_dump(exclude_unset=True)
    if "profile" in data:
        prof = dict(p.profile or {})
        prof.update(data.pop("profile") or {})
        p.profile = prof
    for k, v in data.items():
        setattr(p, k, v)
    db.commit()
    return place_out(p)


@router.delete("/places/{pid}", status_code=204)
def delete_place(pid: uuid.UUID, acc: Access = Depends(project_access), db: Session = Depends(get_db)):
    acc.require("bible")
    db.delete(_own(db, Place, pid, acc, "المكان"))
    db.commit()


# ── events
def _event_refs(db: Session, acc: Access, data: dict) -> dict:
    if "node_id" in data:
        data["node_id"] = _check_ref(db, Node, data["node_id"], acc, "المشهد")
    if "place_id" in data:
        data["place_id"] = _check_ref(db, Place, data["place_id"], acc, "المكان")
    if "participant_ids" in data:
        for pid in data["participant_ids"] or []:
            _check_ref(db, Character, pid, acc, "الشخصية")
    return data


@router.get("/events")
def list_events(acc: Access = Depends(project_access), db: Session = Depends(get_db)):
    return {"items": [event_out(e) for e in db.scalars(select(Event).where(Event.project_id == acc.project.id))]}


@router.post("/events", status_code=201)
def add_event(body: EventIn, acc: Access = Depends(project_access), db: Session = Depends(get_db)):
    acc.require("bible")
    data = _event_refs(db, acc, body.model_dump())
    e = Event(project_id=acc.project.id, **data)
    db.add(e)
    audit.record(db, "event.create", actor_id=acc.user.id, project_id=acc.project.id, object_type="event")
    db.commit()
    return event_out(e)


@router.patch("/events/{eid}")
def patch_event(eid: uuid.UUID, body: EventPatch, acc: Access = Depends(project_access), db: Session = Depends(get_db)):
    acc.require("bible")
    e = _own(db, Event, eid, acc, "الحدث")
    data = body.model_dump(exclude_unset=True)
    clear = data.pop("clear", [])
    data = _event_refs(db, acc, data)
    for k, v in data.items():
        setattr(e, k, v)
    for k in clear:
        if k in ("story_time_start", "story_time_end", "node_id", "place_id", "narration_order", "probability"):
            setattr(e, k, None)
    audit.record(db, "event.update", actor_id=acc.user.id, project_id=acc.project.id, object_type="event",
                 object_id=e.id, meta={"fields": ",".join(list(data) + clear)})
    db.commit()
    return event_out(e)


@router.delete("/events/{eid}", status_code=204)
def delete_event(eid: uuid.UUID, acc: Access = Depends(project_access), db: Session = Depends(get_db)):
    acc.require("bible")
    db.delete(_own(db, Event, eid, acc, "الحدث"))
    db.commit()


# ── relations
@router.get("/edges")
def list_edges(acc: Access = Depends(project_access), db: Session = Depends(get_db)):
    rows = db.scalars(select(EntityEdge).where(EntityEdge.project_id == acc.project.id))
    return {"items": [{"id": str(x.id), "from_type": x.from_type, "from_id": str(x.from_id), "relation": x.relation,
                       "to_type": x.to_type, "to_id": str(x.to_id), "valid_from": x.valid_from,
                       "valid_to": x.valid_to, "epistemic_status": x.epistemic_status, "evidence": x.evidence}
                      for x in rows]}


_TYPE_MODEL = {"character": Character, "place": Place, "event": Event}


@router.post("/edges", status_code=201)
def add_edge(body: EdgeIn, acc: Access = Depends(project_access), db: Session = Depends(get_db)):
    acc.require("bible")
    if body.epistemic_status == "canon":
        acc.require("approve_canon")
    f = _check_ref(db, _TYPE_MODEL[body.from_type], body.from_id, acc, "الطرف")
    t = _check_ref(db, _TYPE_MODEL[body.to_type], body.to_id, acc, "الطرف")
    x = EntityEdge(project_id=acc.project.id, from_type=body.from_type, from_id=f, relation=body.relation,
                   to_type=body.to_type, to_id=t, valid_from=body.valid_from, valid_to=body.valid_to,
                   epistemic_status=body.epistemic_status, evidence=body.evidence)
    db.add(x)
    db.commit()
    return {"id": str(x.id)}


@router.delete("/edges/{xid}", status_code=204)
def delete_edge(xid: uuid.UUID, acc: Access = Depends(project_access), db: Session = Depends(get_db)):
    acc.require("bible")
    db.delete(_own(db, EntityEdge, xid, acc, "العلاقة"))
    db.commit()


# ── facts (causal memory)
@router.get("/facts")
def list_facts(status: str | None = None, acc: Access = Depends(project_access), db: Session = Depends(get_db)):
    q = select(CanonFact).where(CanonFact.project_id == acc.project.id)
    if status:
        q = q.where(CanonFact.epistemic_status == status)
    return {"items": [fact_out(f) for f in db.scalars(q.order_by(CanonFact.created_at))]}


@router.post("/facts", status_code=201)
def add_fact(body: FactIn, acc: Access = Depends(project_access), db: Session = Depends(get_db)):
    acc.require("bible")
    data = body.model_dump()
    sid = data.pop("subject_id")
    f = CanonFact(project_id=acc.project.id, subject_id=uuid.UUID(sid) if sid else None, origin="human", **data)
    db.add(f)
    db.commit()
    return fact_out(f)


@router.post("/facts/{fid}/approve")
def approve_fact(fid: uuid.UUID, acc: Access = Depends(project_access), db: Session = Depends(get_db)):
    """Promote to canon: an authenticated human act by the author (FR13)."""
    acc.require("approve_canon")
    f = _own(db, CanonFact, fid, acc, "الحقيقة")
    f.epistemic_status, f.approved_by, f.approved_at = "canon", acc.user.id, utcnow()
    audit.record(db, "fact.approve", actor_id=acc.user.id, project_id=acc.project.id, object_type="fact", object_id=fid)
    db.commit()
    return fact_out(f)


@router.patch("/facts/{fid}")
def demote_fact(fid: uuid.UUID, status: str, acc: Access = Depends(project_access), db: Session = Depends(get_db)):
    acc.require("approve_canon")
    if status not in ("draft", "hypothesis", "external"):
        raise bad_request("الحالة يجب أن تكون draft أو hypothesis أو external.")
    f = _own(db, CanonFact, fid, acc, "الحقيقة")
    f.epistemic_status, f.approved_by, f.approved_at = status, None, None
    db.commit()
    return fact_out(f)


@router.delete("/facts/{fid}", status_code=204)
def delete_fact(fid: uuid.UUID, acc: Access = Depends(project_access), db: Session = Depends(get_db)):
    f = _own(db, CanonFact, fid, acc, "الحقيقة")
    acc.require("approve_canon" if f.epistemic_status == "canon" else "bible")
    db.delete(f)
    db.commit()


# ── calendars (story time in the author's calendar)
@router.get("/calendar/convert")
def calendar_convert(calendar: str, year: int, month: int | None = None, day: int | None = None,
                     acc: Access = Depends(project_access)):
    from ..calendars import convert

    try:
        return convert(calendar, year, month, day)
    except ValueError as e:
        raise bad_request(str(e)) from e


# ── views
@router.get("/timeline")
def timeline(acc: Access = Depends(project_access), db: Session = Depends(get_db)):
    """Story time vs narration order. Scenes contribute their own story_time when set."""
    events = [event_out(e) for e in db.scalars(select(Event).where(Event.project_id == acc.project.id))]
    from ..models import Manuscript

    scenes = []
    order = 0
    for m in db.scalars(select(Manuscript).where(Manuscript.project_id == acc.project.id).order_by(Manuscript.position)):
        nodes = ordered_nodes(db, m.id)
        lb = labels(nodes)
        for n in nodes:
            if n.type in ("chapter", "scene"):
                order += 1
                t = (n.meta or {}).get("story_time")
                scenes.append({"node_id": str(n.id), "label": lb.get(n.id, ""), "type": n.type, "narration_index": order,
                               "story_time": t if isinstance(t, (int, float)) else None,
                               "story_time_label": (n.meta or {}).get("story_time_label", "")})
    return {"events": events, "scenes": scenes}


@router.get("/graph")
def graph(acc: Access = Depends(project_access), db: Session = Depends(get_db)):
    pid = acc.project.id
    nodes = [{"id": str(c.id), "type": "character", "label": c.canonical_name}
             for c in db.scalars(select(Character).where(Character.project_id == pid))]
    nodes += [{"id": str(p.id), "type": "place", "label": p.name} for p in db.scalars(select(Place).where(Place.project_id == pid))]
    edges = [{"id": str(x.id), "from": str(x.from_id), "to": str(x.to_id), "label": x.relation,
              "status": x.epistemic_status, "evidence": x.evidence}
             for x in db.scalars(select(EntityEdge).where(EntityEdge.project_id == pid))]
    for e in db.scalars(select(Event).where(Event.project_id == pid)):
        ps = e.participant_ids or []
        for i, a in enumerate(ps):
            for b in ps[i + 1:]:
                edges.append({"id": f"{e.id}:{a}:{b}", "from": a, "to": b, "label": e.title, "status": "event",
                              "evidence": [{"kind": "entity", "entity_type": "event", "entity_id": str(e.id)}]})
        if e.place_id:
            for a in ps:
                edges.append({"id": f"{e.id}:{a}:p", "from": a, "to": str(e.place_id), "label": e.title,
                              "status": "event", "evidence": []})
    return {"nodes": nodes, "edges": edges}
