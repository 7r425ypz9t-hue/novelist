"""Domain data model (SYSTEM_SPEC §7, extended per docs/SPEC_REVIEW.md).

Conventions: UUID primary keys, UTC timestamps, every project-scoped row carries `project_id`
so that authorization can be enforced at row level with one predicate.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .crypto import EncryptedJSON, EncryptedText
from .db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_id() -> uuid.UUID:
    return uuid.uuid4()


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


# ───────────────────────────── identity ─────────────────────────────


class User(TimestampMixin, Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(200), default="")
    password_hash: Mapped[str] = mapped_column(String(300))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    settings: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    user_agent: Mapped[str] = mapped_column(String(300), default="")


# ───────────────────────────── projects ─────────────────────────────


class Project(TimestampMixin, Base):
    __tablename__ = "projects"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    language: Mapped[str] = mapped_column(String(16), default="ar")
    genre: Mapped[str] = mapped_column(String(120), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    logline: Mapped[str] = mapped_column(Text, default="")
    privacy_mode: Mapped[str] = mapped_column(String(16), default="private")  # private | shared
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | archived
    word_goal: Mapped[int] = mapped_column(Integer, default=0)
    ai_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    nlqi_weights: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # Fictional-world calendars: [{id, name, suffix, epoch, ratio, months[]}] (docs/SPEC_REVIEW.md R4)
    calendars: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, default=list, nullable=True)


class Membership(TimestampMixin, Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("user_id", "project_id"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16))  # owner | editor | commenter | reader
    permissions: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Consent(Base):
    """Explicit, revocable consents (external AI transfer, style samples, source usage)."""

    __tablename__ = "consents"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=True
    )
    kind: Mapped[str] = mapped_column(String(32))  # external_ai | style_sample | source_usage
    scope: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# ───────────────────────────── manuscript ─────────────────────────────


class Manuscript(TimestampMixin, Base):
    __tablename__ = "manuscripts"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    subtitle: Mapped[str] = mapped_column(String(300), default="")
    author_name: Mapped[str] = mapped_column(String(200), default="")
    position: Mapped[int] = mapped_column(Integer, default=0)


class Node(TimestampMixin, Base):
    """Part → chapter → scene. IDs are stable across moves and renumbering (FR03)."""

    __tablename__ = "nodes"
    __table_args__ = (Index("ix_nodes_parent_pos", "manuscript_id", "parent_id", "position"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    manuscript_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("manuscripts.id", ondelete="CASCADE"), index=True)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("nodes.id", ondelete="CASCADE"), nullable=True, index=True
    )
    type: Mapped[str] = mapped_column(String(16))  # part | chapter | scene
    position: Mapped[int] = mapped_column(Integer, default=0)
    title: Mapped[str] = mapped_column(String(300), default="")
    status: Mapped[str] = mapped_column(String(16), default="draft")  # idea | draft | revised | final
    # Scene matrix (FR10): goal, conflict, outcome, pov_character_id, place_id, story_time, story_time_label,
    # character_ids, new_information, synopsis
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # Soft delete: removing a node moves it to the trash; its revisions are never erased (FR06).
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    node_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("nodes.id", ondelete="CASCADE"), unique=True)
    content_json: Mapped[dict[str, Any]] = mapped_column(EncryptedJSON, default=dict)
    text_plain: Mapped[str] = mapped_column(EncryptedText, default="")
    content_hash: Mapped[str] = mapped_column(String(64), default="")
    version: Mapped[int] = mapped_column(Integer, default=0)
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    current_revision_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)

    node: Mapped[Node] = relationship()


class Revision(Base):
    """Immutable snapshot. Never updated or deleted except by full project deletion (FR06)."""

    __tablename__ = "revisions"
    __table_args__ = (
        UniqueConstraint("document_id", "revision_no"),
        UniqueConstraint("document_id", "client_save_id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    revision_no: Mapped[int] = mapped_column(Integer)
    parent_revision_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    kind: Mapped[str] = mapped_column(String(16))  # autosave | checkpoint | restore | proposal | import
    author_type: Mapped[str] = mapped_column(String(24))  # human | human_accepted_ai | import
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    label: Mapped[str] = mapped_column(String(200), default="")
    content_json: Mapped[dict[str, Any]] = mapped_column(EncryptedJSON)
    text_plain: Mapped[str] = mapped_column(EncryptedText)
    checksum: Mapped[str] = mapped_column(String(64))
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    client_save_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_proposal_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class Comment(TimestampMixin, Base):
    __tablename__ = "comments"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    anchor: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # {block, quote}
    body: Mapped[str] = mapped_column(EncryptedText)
    state: Mapped[str] = mapped_column(String(16), default="open")


# ───────────────────────────── story bible ─────────────────────────────


class Character(TimestampMixin, Base):
    __tablename__ = "characters"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    canonical_name: Mapped[str] = mapped_column(String(200))
    aliases: Mapped[list[str]] = mapped_column(JSON, default=list)
    # profile: birth_year, death_year, goal, obstacle, secret, arc, description, role
    profile: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="active")


class Place(TimestampMixin, Base):
    __tablename__ = "places"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    aliases: Mapped[list[str]] = mapped_column(JSON, default=list)
    profile: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # description, constraints, period
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)


class Event(TimestampMixin, Base):
    """Story time vs narration order (FR09). Unknown/ranged/probabilistic times are first-class."""

    __tablename__ = "events"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    summary: Mapped[str] = mapped_column(Text, default="")
    story_time_start: Mapped[float | None] = mapped_column(Float, nullable=True)  # story year (decimal)
    story_time_end: Mapped[float | None] = mapped_column(Float, nullable=True)
    time_label: Mapped[str] = mapped_column(String(120), default="")
    uncertainty: Mapped[str] = mapped_column(String(16), default="exact")  # exact | approx | range | unknown
    probability: Mapped[float | None] = mapped_column(Float, nullable=True)
    narration_order: Mapped[int | None] = mapped_column(Integer, nullable=True)
    node_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("nodes.id", ondelete="SET NULL"), nullable=True)
    place_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("places.id", ondelete="SET NULL"), nullable=True)
    participant_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    kind: Mapped[str] = mapped_column(String(32), default="event")  # event | birth | death | travel


class EntityEdge(TimestampMixin, Base):
    __tablename__ = "entity_edges"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    from_type: Mapped[str] = mapped_column(String(16))
    from_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    relation: Mapped[str] = mapped_column(String(120))
    to_type: Mapped[str] = mapped_column(String(16))
    to_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    valid_from: Mapped[float | None] = mapped_column(Float, nullable=True)
    valid_to: Mapped[float | None] = mapped_column(Float, nullable=True)
    epistemic_status: Mapped[str] = mapped_column(String(16), default="draft")
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)


class CanonFact(TimestampMixin, Base):
    """Causal memory unit (§9). Becoming `canon` requires a human approval event (FR13)."""

    __tablename__ = "canon_facts"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    subject_type: Mapped[str] = mapped_column(String(16))  # character | place | event | world
    subject_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    subject_label: Mapped[str] = mapped_column(String(200), default="")
    predicate: Mapped[str] = mapped_column(String(120))
    object: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # {"value": ..., "unit": ...}
    statement: Mapped[str] = mapped_column(Text, default="")
    epistemic_status: Mapped[str] = mapped_column(String(16), default="draft")  # canon|draft|hypothesis|external
    valid_from: Mapped[float | None] = mapped_column(Float, nullable=True)
    valid_to: Mapped[float | None] = mapped_column(Float, nullable=True)
    narrative_order: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_refs: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    origin: Mapped[str] = mapped_column(String(16), default="human")  # human | agent | extraction
    approved_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Conflict(TimestampMixin, Base):
    __tablename__ = "conflicts"
    __table_args__ = (UniqueConstraint("project_id", "fingerprint"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    rule: Mapped[str] = mapped_column(String(48))
    conflict_type: Mapped[str] = mapped_column(String(48))
    severity: Mapped[str] = mapped_column(String(8))  # low | medium | high
    title: Mapped[str] = mapped_column(String(300))
    explanation: Mapped[str] = mapped_column(Text, default="")
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    fingerprint: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(16), default="open")  # open | resolved | waived | dismissed
    resolution_note: Mapped[str] = mapped_column(Text, default="")
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ───────────────────────────── research ─────────────────────────────


class SourceFile(TimestampMixin, Base):
    __tablename__ = "source_files"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(300))
    file_type: Mapped[str] = mapped_column(String(8))
    size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    object_key: Mapped[str] = mapped_column(String(400))
    title: Mapped[str] = mapped_column(String(300), default="")
    author: Mapped[str] = mapped_column(String(300), default="")
    license_state: Mapped[str] = mapped_column(String(24))  # owned|licensed|public_domain|permission|unknown
    usage_consent: Mapped[bool] = mapped_column(Boolean, default=False)
    ingestion_status: Mapped[str] = mapped_column(String(16), default="pending")
    ingestion_error: Mapped[str] = mapped_column(Text, default="")
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    flagged_chunks: Mapped[int] = mapped_column(Integer, default=0)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(Uuid)


class SourceChunk(Base):
    __tablename__ = "source_chunks"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    source_file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source_files.id", ondelete="CASCADE"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    locator: Mapped[str] = mapped_column(String(120))
    content: Mapped[str] = mapped_column(EncryptedText)
    normalized: Mapped[str] = mapped_column(EncryptedText)
    checksum: Mapped[str] = mapped_column(String(64))
    flags: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Citation(TimestampMixin, Base):
    """Links a manuscript claim to a source chunk, or marks it explicitly `unverified` (FR22)."""

    __tablename__ = "citations"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    claim_text: Mapped[str] = mapped_column(Text)
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    span: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    source_chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("source_chunks.id", ondelete="SET NULL"), nullable=True
    )
    verification_state: Mapped[str] = mapped_column(String(16), default="unverified")  # verified|unverified|disputed
    note: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid)


# ───────────────────────────── agents ─────────────────────────────


class AgentRun(TimestampMixin, Base):
    __tablename__ = "agent_runs"
    __table_args__ = (UniqueConstraint("project_id", "idempotency_key"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    agent_id: Mapped[str] = mapped_column(String(8))
    skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    goal: Mapped[str] = mapped_column(Text, default="")
    scope: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    base_revisions: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    provider: Mapped[str] = mapped_column(String(32), default="disabled")
    model_id: Mapped[str] = mapped_column(String(120), default="deterministic")
    risk_level: Mapped[str] = mapped_column(String(8), default="LOW")
    idempotency_key: Mapped[str] = mapped_column(String(80))
    input_hash: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(16), default="queued")
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    cost_estimate_usd: Mapped[float] = mapped_column(Float, default=0.0)
    tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    output: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(Text, default="")
    requested_by: Mapped[uuid.UUID] = mapped_column(Uuid)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Proposal(TimestampMixin, Base):
    __tablename__ = "proposals"
    __table_args__ = (UniqueConstraint("project_id", "fingerprint"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True)
    agent_id: Mapped[str] = mapped_column(String(8))
    skill_id: Mapped[str] = mapped_column(String(8))
    kind: Mapped[str] = mapped_column(String(16), default="patch")  # patch | note | fact
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=True, index=True
    )
    target_revision_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    patch: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    title: Mapped[str] = mapped_column(String(300), default="")
    rationale: Mapped[str] = mapped_column(Text, default="")
    evidence_refs: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    risk_level: Mapped[str] = mapped_column(String(8), default="MEDIUM")
    certainty: Mapped[str] = mapped_column(String(16), default="inferred")
    fingerprint: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(16), default="pending")  # pending|accepted|rejected|stale
    decided_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_note: Mapped[str] = mapped_column(Text, default="")
    result_revision_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)


class StyleProfile(TimestampMixin, Base):
    __tablename__ = "style_profiles"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    features: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    consent_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    sample_count: Mapped[int] = mapped_column(Integer, default=0)
    sample_hashes: Mapped[list[str]] = mapped_column(JSON, default=list)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Assessment(TimestampMixin, Base):
    """Human NLQI rubric scores (experimental index, never presented as objective)."""

    __tablename__ = "assessments"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    node_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("nodes.id", ondelete="SET NULL"), nullable=True)
    rater_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    rater_label: Mapped[str] = mapped_column(String(120), default="")
    scores: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # dimension -> 0..10
    notes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # dimension -> justification


class Export(TimestampMixin, Base):
    __tablename__ = "exports"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    format: Mapped[str] = mapped_column(String(8))  # docx | pdf | epub | md | data
    status: Mapped[str] = mapped_column(String(16), default="queued")
    object_key: Mapped[str] = mapped_column(String(400), default="")
    filename: Mapped[str] = mapped_column(String(300), default="")
    sha256: Mapped[str] = mapped_column(String(64), default="")
    size: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, default="")
    requested_by: Mapped[uuid.UUID] = mapped_column(Uuid)


class AuditEvent(Base):
    """Redacted audit log: never stores manuscript text (FR19, §12)."""

    __tablename__ = "audit_events"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    actor_type: Mapped[str] = mapped_column(String(16), default="user")  # user | agent | system
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    object_type: Mapped[str] = mapped_column(String(32), default="")
    object_id: Mapped[str] = mapped_column(String(64), default="")
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    metadata_redacted: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


@event.listens_for(Revision, "before_update")
def _revisions_are_immutable(_mapper, _conn, _target):  # pragma: no cover - guarded by tests
    raise RuntimeError("revisions are immutable")
