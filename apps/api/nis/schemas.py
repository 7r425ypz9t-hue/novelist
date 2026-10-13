"""Request models (validation at the edge — Pydantic v2)."""

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class RegisterIn(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=10, max_length=200)
    display_name: str = Field(default="", max_length=200)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip().lower()
        if "@" not in v or v.startswith("@") or v.endswith("@"):
            raise ValueError("بريد غير صالح")
        return v


class LoginIn(BaseModel):
    email: str
    password: str


class ProjectIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    language: str = Field(default="ar", max_length=16)
    genre: str = Field(default="", max_length=120)
    description: str = Field(default="", max_length=20000)
    logline: str = Field(default="", max_length=2000)
    privacy_mode: Literal["private", "shared"] = "private"
    word_goal: int = Field(default=0, ge=0, le=2_000_000)
    manuscript_title: str | None = None
    author_name: str = Field(default="", max_length=200)


class ProjectPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    genre: str | None = None
    description: str | None = None
    logline: str | None = None
    privacy_mode: Literal["private", "shared"] | None = None
    status: Literal["active", "archived"] | None = None
    word_goal: int | None = Field(default=None, ge=0, le=2_000_000)
    ai_enabled: bool | None = None


class MemberIn(BaseModel):
    email: str
    role: Literal["editor", "commenter", "reader"]
    permissions: dict[str, bool] = {}


class ManuscriptIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    subtitle: str = ""
    author_name: str = ""


class ManuscriptPatch(BaseModel):
    title: str | None = None
    subtitle: str | None = None
    author_name: str | None = None


class NodeIn(BaseModel):
    manuscript_id: str | None = None
    parent_id: str | None = None
    type: Literal["part", "chapter", "scene"]
    title: str = Field(default="", max_length=300)
    position: int | None = None
    meta: dict[str, Any] = {}


class NodePatch(BaseModel):
    title: str | None = Field(default=None, max_length=300)
    status: Literal["idea", "draft", "revised", "final"] | None = None
    meta: dict[str, Any] | None = None


class ReorderIn(BaseModel):
    parent_id: str | None = None
    position: int = Field(ge=0)


class DocumentPut(BaseModel):
    content_json: dict[str, Any]
    kind: Literal["autosave", "checkpoint"] = "autosave"
    label: str = Field(default="", max_length=200)
    client_save_id: str | None = Field(default=None, max_length=64)


class CommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=8000)
    anchor: dict[str, Any] = {}


class CharacterIn(BaseModel):
    canonical_name: str = Field(min_length=1, max_length=200)
    aliases: list[str] = []
    profile: dict[str, Any] = {}
    status: Literal["active", "archived"] = "active"


class CharacterPatch(BaseModel):
    canonical_name: str | None = None
    aliases: list[str] | None = None
    profile: dict[str, Any] | None = None
    status: Literal["active", "archived"] | None = None


class PlaceIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    aliases: list[str] = []
    profile: dict[str, Any] = {}
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)


class PlacePatch(BaseModel):
    name: str | None = None
    aliases: list[str] | None = None
    profile: dict[str, Any] | None = None
    lat: float | None = None
    lon: float | None = None


class EventIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    summary: str = ""
    story_time_start: float | None = None
    story_time_end: float | None = None
    time_label: str = ""
    uncertainty: Literal["exact", "approx", "range", "unknown"] = "exact"
    probability: float | None = Field(default=None, ge=0, le=1)
    narration_order: int | None = None
    node_id: str | None = None
    place_id: str | None = None
    participant_ids: list[str] = []
    kind: Literal["event", "birth", "death", "travel"] = "event"


class EventPatch(BaseModel):
    title: str | None = None
    summary: str | None = None
    story_time_start: float | None = None
    story_time_end: float | None = None
    time_label: str | None = None
    uncertainty: Literal["exact", "approx", "range", "unknown"] | None = None
    probability: float | None = None
    narration_order: int | None = None
    node_id: str | None = None
    place_id: str | None = None
    participant_ids: list[str] | None = None
    kind: Literal["event", "birth", "death", "travel"] | None = None
    clear: list[str] = []  # field names to set to null explicitly


class EdgeIn(BaseModel):
    from_type: Literal["character", "place", "event"]
    from_id: str
    relation: str = Field(min_length=1, max_length=120)
    to_type: Literal["character", "place", "event"]
    to_id: str
    valid_from: float | None = None
    valid_to: float | None = None
    epistemic_status: Literal["canon", "draft", "hypothesis", "external"] = "draft"
    evidence: list[dict[str, Any]] = []


class FactIn(BaseModel):
    subject_type: Literal["character", "place", "event", "world"] = "world"
    subject_id: str | None = None
    subject_label: str = ""
    predicate: str = Field(min_length=1, max_length=120)
    object: dict[str, Any] = {}
    statement: str = ""
    epistemic_status: Literal["draft", "hypothesis", "external"] = "draft"  # canon only via approve
    valid_from: float | None = None
    valid_to: float | None = None
    source_refs: list[dict[str, Any]] = []
    confidence: float | None = Field(default=None, ge=0, le=1)


class ResolveIn(BaseModel):
    action: Literal["resolve", "waive", "dismiss", "reopen"]
    note: str = Field(default="", max_length=4000)


class SourcePatch(BaseModel):
    title: str | None = None
    author: str | None = None
    license_state: Literal["owned", "licensed", "public_domain", "permission", "unknown"] | None = None
    usage_consent: bool | None = None


class QueryIn(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    k: int = Field(default=6, ge=1, le=20)


class CitationIn(BaseModel):
    claim_text: str = Field(min_length=1, max_length=4000)
    document_id: str | None = None
    span: dict[str, Any] = {}
    source_chunk_id: str | None = None
    note: str = ""


class RunIn(BaseModel):
    project_id: str
    agent_id: str = Field(pattern=r"^A\d{2}$")
    skills: list[str] | None = None
    goal: str = ""
    node_ids: list[str] = []
    idempotency_key: str = Field(min_length=8, max_length=80)
    use_model: bool = False
    acknowledge_external: bool = False
    confirm_high_risk: bool = False


class DecisionIn(BaseModel):
    note: str = ""
    edited_ops: list[dict[str, Any]] | None = None
    allow_rebase: bool = False
    as_canon: bool = False


class ExportIn(BaseModel):
    format: Literal["docx", "pdf", "epub", "md"]
    manuscript_id: str | None = None


class DeleteProjectIn(BaseModel):
    confirm_title: str


class ConsentIn(BaseModel):
    kind: Literal["external_ai"]
    acknowledge_destination: str = Field(min_length=1)


class StyleIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    samples: list[str] = Field(min_length=1, max_length=50)
    rights_basis: Literal["own_work", "licensed_with_permission", "third_party", "unknown"]
    declaration: bool
    imitate_author: str | None = None


class AssessmentIn(BaseModel):
    node_id: str | None = None
    rater_label: str = Field(default="", max_length=120)
    scores: dict[str, float]
    notes: dict[str, str] = {}


class WeightsIn(BaseModel):
    weights: dict[str, float]


class ImportCommitIn(BaseModel):
    manuscript_id: str | None = None
    chapters: list[dict[str, Any]] = Field(min_length=1, max_length=2000)


class CalendarDef(BaseModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,31}$")
    name: str = Field(min_length=1, max_length=80)
    suffix: str = Field(default="", max_length=20)
    epoch: float = 0.0
    ratio: float = Field(default=1.0, gt=0, le=1000)
    months: list[str] = Field(default=[], max_length=40)


class CalendarsIn(BaseModel):
    calendars: list[CalendarDef] = Field(max_length=12)
