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
