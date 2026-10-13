export type Role = "owner" | "editor" | "commenter" | "reader";

export interface User { id: string; email: string; display_name: string; is_admin: boolean }

export interface Project {
  id: string; title: string; language: string; genre: string; description: string; logline: string;
  privacy_mode: "private" | "shared"; status: string; word_goal: number; ai_enabled: boolean; role: Role | null;
  words?: number; permissions?: string[]; created_at: string; updated_at?: string;
  manuscripts?: { id: string; title: string; subtitle: string; author_name: string }[];
}

export interface TreeNode {
  id: string; manuscript_id: string; parent_id: string | null; type: "part" | "chapter" | "scene";
  title: string; position: number; status: string; meta: Record<string, any>; document_id: string | null;
  word_count: number; label: string;
}

export interface Doc {
  id: string; node_id: string; content_json: any; version: number; etag: string; word_count: number;
  current_revision_id: string | null; updated_at: string;
}

export interface Revision {
  id: string; revision_no: number; kind: string; author_type: string; label: string; checksum: string;
  word_count: number; created_at: string; source_proposal_id: string | null;
}

export interface Evidence {
  kind: "text" | "entity" | "node" | "source" | "quote"; label?: string; document_id?: string; node_id?: string;
  start?: number; end?: number; excerpt?: string; quote?: string; note?: string; entity_type?: string;
  field?: string; value?: unknown; locator?: string; chunk_id?: string; epistemic_status?: string;
}

export interface ConflictItem {
  id: string; rule: string; conflict_type: string; severity: "high" | "medium" | "low"; title: string;
  explanation: string; evidence: Evidence[]; state: string; resolution_note: string; created_at: string;
}

export interface Proposal {
  id: string; run_id: string | null; agent_id: string; skill_id: string; kind: "patch" | "note" | "fact";
  document_id: string | null; target_revision_id: string | null; patch: any; title: string; rationale: string;
  evidence_refs: Evidence[]; risk_level: string; certainty: string; state: string; created_at: string;
  preview?: { applicable: boolean; stale?: boolean; error?: string; diff: DiffSeg[] };
}

export interface DiffSeg { op: "equal" | "insert" | "delete"; text: string }

export interface Run {
  id: string; agent_id: string; agent_name: string; skills: string[]; goal: string; status: string;
  risk_level: string; provider: string; model_id: string; tokens_used: number; steps: any[]; created_at: string;
  finished_at: string | null; output?: any; error?: string; deduplicated?: boolean; attempts?: number;
  started_at?: string | null; progress?: { done: number; failed: number; total: number; current: string | null };
}

export interface Character { id: string; canonical_name: string; aliases: string[]; profile: Record<string, any>; status: string }
export interface Place { id: string; name: string; aliases: string[]; profile: Record<string, any>; lat: number | null; lon: number | null }
export interface EventItem {
  id: string; title: string; summary: string; story_time_start: number | null; story_time_end: number | null;
  time_label: string; uncertainty: string; narration_order: number | null; node_id: string | null;
  place_id: string | null; participant_ids: string[]; kind: string; probability: number | null;
}
export interface Fact {
  id: string; subject_type: string; subject_id: string | null; subject_label: string; predicate: string;
  object: { value?: unknown }; statement: string; epistemic_status: string; origin: string; source_refs: any[];
  approved_at: string | null;
}
export interface Source {
  id: string; filename: string; title: string; author: string; file_type: string; size: number; license_state: string;
  usage_consent: boolean; ingestion_status: string; page_count: number; flagged_chunks: number; usable: boolean;
  created_at: string;
}
export interface Hit {
  chunk_id: string; source_id: string; source_title: string; locator: string; page: number | null; score: number;
  term_coverage: number; content: string; suspicious_instructions: string[];
  matched_via?: { term: string; matched: string; kind: "morph" | "alias" | "synonym" }[];
}
