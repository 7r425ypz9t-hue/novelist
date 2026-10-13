# Decisions

Spec decisions (kept):
- Arabic RTL first; authors retain final control of all manuscript edits.
- PostgreSQL edge tables before any graph database.
- External AI providers optional and consent-gated.

Implementation decisions (2026-10-13, rationale in docs/SPEC_REVIEW.md §7):
- D-01 Vite + React SPA served by FastAPI from the same origin instead of Next.js (private editor, strict CSP, single-process local mode). Tiptap kept.
- D-02 SQLite (local single-user) and PostgreSQL 16 (server) both supported; the full test suite runs on both.
- D-03 Lexical BM25 retrieval with Arabic normalization + light stemming before embeddings; evidence = term coverage ≥ 60% and ≥ 2 terms, otherwise "غير متحقق".
- D-04 In-process orchestrator with DB-persisted checkpoints instead of Redis/LangGraph for v1.
- D-05 Capability-object tool model: agents receive a ToolContext exposing only five tools.
- D-06 Status codes: 428 missing If-Match, 412 stale write, 409 stale proposal; non-members get 404.
- D-07 Soft delete for manuscript nodes; revisions are immutable (ORM guard) and only removed with the whole project.
- D-08 New skill SK21 for A08 (memory keeper); A06 added to the A00 planning stage.
- D-09 PDF via ReportLab + arabic-reshaper + python-bidi with an embedded OFL Noto Naskh Arabic (Arabic + Latin subsets merged); optional tashkeel is dropped in PDF only.
- D-10 No hard-coded model prices or provider retention claims; costs only when the operator configures prices.
- D-11 Encryption at rest with one server key (AES-256-GCM, `enc:v1:` prefix, legacy plaintext readable); per-project author keys deferred.
- D-12 Story time stays a Gregorian decimal axis; Hijri input converted with the tabular calendar, original wording kept in the label.
- D-13 PDF engine: WeasyPrint (optional extra `pdf`, needs system Pango) preferred; ReportLab fallback; D-09's tashkeel limitation now applies only to the fallback.
- D-15 Product renamed «كاتب» (Kateb) in every user-facing surface; internal identifiers (`nis` package, `NIS_*` env vars, `nis` CLI) unchanged for deployment compatibility.
- D-14 Retrieval stays local: BM25 + morphological neighbours (bigram Dice ≥ 0.62) + curated synonyms + Story Bible aliases, each expansion reported; embeddings deferred by owner decision.
- D-16 Owner palette adopted; light theme default. Per-project operator-blind keys declined by owner.
- D-17 Arabic page eyebrows; fluid type scale (viewport clamp for page text, container queries for card titles/KPIs); top bar 64px; fluid sidebar and writing-room panes.
- D-18 Tagline «استديو الرواية»; manuscript editor text fixed at 14px with line-height 1.5 (owner request; revised from 1; tokens `--fs-paper`, `--paper-leading`); exports keep their own print typography; proposal diffs share the manuscript size (leading +0.3 for change highlights); AT01 asserts 14px/21px. Sidebar on light beige (`--sidebar-bg`, dark-theme counterpart), axe AA clean.
