"""Capability-scoped tool context handed to skills.

Skills receive this object and nothing else: it can read the run's project only, retrieve sources as
untrusted data, and *create* proposals. There is deliberately no method to accept proposals, modify canon,
delete, publish or run shell commands, so neither a model reply nor a malicious retrieved document can
escalate an agent's rights (AGENTS.md «صلاحيات الأدوات», AT11).
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from functools import cached_property
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    CanonFact,
    Character,
    Document,
    Event,
    Manuscript,
    Node,
    Place,
    Project,
    Proposal,
    Revision,
    StyleProfile,
)
from ..security import sha256_hex
from ..services import research
from ..services.manuscript import labels, ordered_nodes
from ..text import blocks


@dataclass
class Scene:
    node: Node
    doc: Document
    label: str
    chapter_id: uuid.UUID | None

    @property
    def text(self) -> str:
        return self.doc.text_plain or ""

    @property
    def blocks(self) -> list[dict[str, Any]]:
        return blocks(self.doc.content_json)


@dataclass
class SkillResult:
    summary: str = ""
    findings: list[dict[str, Any]] = field(default_factory=list)
    citations: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    uncertainty: str = "medium"
    proposals_created: int = 0
    tokens: int = 0

    def find(self, claim: str, *, certainty: str = "inferred", kind: str = "objective", area: str = "",
             evidence: list[dict[str, Any]] | None = None) -> None:
        self.findings.append({"claim": claim, "certainty": certainty, "kind": kind, "area": area,
                              "evidence_refs": evidence or []})

    def as_dict(self) -> dict[str, Any]:
        return {"summary": self.summary, "findings": self.findings, "citations": self.citations,
                "warnings": self.warnings, "metrics": self.metrics, "uncertainty": self.uncertainty,
                "proposals_created": self.proposals_created, "requires_approval": self.proposals_created > 0}


class ToolContext:
    ALLOWED = ("read_project", "read_revision", "search_canon", "retrieve_sources", "create_proposal")

    def __init__(self, db: Session, project_id: uuid.UUID, run_id: uuid.UUID | None, agent_id: str,
                 scope_node_ids: list[str] | None = None):
        self._db = db
        self.project_id = project_id
        self.run_id = run_id
        self.agent_id = agent_id
        self._scope = {str(s) for s in scope_node_ids or []}

    # ── read_project
    @cached_property
    def project(self) -> Project:
        p = self._db.get(Project, self.project_id)
        if p is None:  # explicit, not `assert`: survives python -O
            raise LookupError(f"project {self.project_id} not found for agent context")
        return p

    @cached_property
    def nodes(self) -> list[Node]:
        out: list[Node] = []
        for m in self._db.scalars(select(Manuscript).where(Manuscript.project_id == self.project_id)
                                  .order_by(Manuscript.position)):
            out.extend(ordered_nodes(self._db, m.id))
        return out

    @cached_property
    def labels(self) -> dict[uuid.UUID, str]:
        return labels(self.nodes)

    @cached_property
    def scenes(self) -> list[Scene]:
        """Text-bearing nodes (chapters with text and scenes) in reading order, filtered by run scope."""
        docs = {d.node_id: d for d in self._db.scalars(select(Document).where(Document.project_id == self.project_id))}
        out = []
        for n in self.nodes:
            d = docs.get(n.id)
            if d is None:
                continue
            if self._scope and str(n.id) not in self._scope and str(n.parent_id) not in self._scope:
                continue
            chapter = n.id if n.type == "chapter" else n.parent_id
            out.append(Scene(n, d, self.labels.get(n.id, ""), chapter))
        return out

    @cached_property
    def characters(self) -> list[Character]:
        return list(self._db.scalars(select(Character).where(Character.project_id == self.project_id)))

    @cached_property
    def places(self) -> list[Place]:
        return list(self._db.scalars(select(Place).where(Place.project_id == self.project_id)))

    @cached_property
    def events(self) -> list[Event]:
        return list(self._db.scalars(select(Event).where(Event.project_id == self.project_id)))

    def style_profile(self) -> StyleProfile | None:
        return self._db.scalar(select(StyleProfile).where(StyleProfile.project_id == self.project_id,
                                                          StyleProfile.deleted_at.is_(None))
                               .order_by(StyleProfile.created_at.desc()))

    # ── read_revision
    def read_revision(self, revision_id: uuid.UUID) -> Revision | None:
        r = self._db.get(Revision, revision_id)
        return r if r and r.project_id == self.project_id else None

    # ── search_canon
    def search_canon(self, subject_id: uuid.UUID | None = None) -> list[CanonFact]:
        q = select(CanonFact).where(CanonFact.project_id == self.project_id)
        if subject_id:
            q = q.where(CanonFact.subject_id == subject_id)
        return list(self._db.scalars(q))

    # ── retrieve_sources (always returned as untrusted data)
    def retrieve_sources(self, query: str, k: int = 4) -> dict[str, Any]:
        return research.search(self._db, self.project_id, query, k=k)

    # ── create_proposal (dedupe by fingerprint → idempotent across retries, AT20)
    def create_proposal(self, *, skill_id: str, title: str, rationale: str, kind: str = "patch",
                        document: Document | None = None, ops: list[dict[str, Any]] | None = None,
                        payload: dict[str, Any] | None = None, evidence: list[dict[str, Any]] | None = None,
                        risk: str = "MEDIUM", certainty: str = "inferred") -> bool:
        patch: dict[str, Any] = {"ops": ops or []} if kind == "patch" else dict(payload or {})
        fp = sha256_hex(json.dumps({
            "doc": str(document.id) if document else None,
            "base": str(document.current_revision_id) if document else None,
            "kind": kind, "skill": skill_id, "patch": patch,
        }, ensure_ascii=False, sort_keys=True))
        exists = self._db.scalar(select(Proposal.id).where(Proposal.project_id == self.project_id,
                                                           Proposal.fingerprint == fp))
        if exists:
            return False
        self._db.add(Proposal(
            project_id=self.project_id, run_id=self.run_id, agent_id=self.agent_id, skill_id=skill_id, kind=kind,
            document_id=document.id if document else None,
            target_revision_id=document.current_revision_id if document else None,
            patch=patch, title=title[:300], rationale=rationale, evidence_refs=evidence or [], risk_level=risk,
            certainty=certainty, fingerprint=fp,
        ))
        self._db.flush()
        return True

    @property
    def db_for_continuity(self) -> Session:
        """Continuity scan writes analysis records (conflicts), never manuscript or canon."""
        return self._db
