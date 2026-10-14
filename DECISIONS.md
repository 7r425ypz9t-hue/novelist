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
- D-19 Owner font «أضواء السلف» (adwa-assalaf) is first in the UI and manuscript stacks via `local()` only, Arabic code points only (UI copy `size-adjust: 112%`, manuscript at true 14px). Its embedded notice identifies it as a derivative of a commercial Linotype design, so it is not committed, served, or embedded in exports; without it installed, the bundled OFL faces apply and exports keep Noto Naskh Arabic.
- D-20 Amiri (OFL 1.1, The Amiri Project Authors; release 1.003) is the single typeface of the product and of every export (DOCX/PDF/EPUB), replacing Noto Naskh Arabic and the local-only face of D-19 (superseded). UI uses a `size-adjust: 112%` declaration of the same files; the manuscript stays at true 14px/1.5. Amiri carries ⁂, so the ReportLab fallback now prints the real scene-break glyph.
- D-21 Labels: dashboard eyebrow «لوحة الإدارة», page and nav «سكرتارية التحرير»; the dashboard subtitle is the fixed motto «كلما اتسعت الرؤية ضاقت العبارة» (the project logline remains on the library cards and in Settings).
- D-22 Find & replace is Arabic-aware: one literal pattern (never user regex) mirrored in `nis.text.arabic_pattern` and `lib/arabic.ts → arabicPattern`, skipping tashkeel/tatweel and unifying أ/إ/آ/ٱ/ا, ي/ى/ئ, ه/ة, و/ؤ and Western/Eastern digits (each switchable), optional whole word; matches stay inside one paragraph and span formatting runs. Manuscript-wide search is read-only (`GET /projects/{id}/manuscript/search`, member-only); replacement stays per unit so every change remains one undoable edit and one revision of that unit.
- D-23 «كلمة كاملة» accepts attached proclitics by default (و، ف، ب، ك، ل، ال and their combinations; switchable), consumed only at a word start and kept outside the highlighted/replaced group `w` — the first design (lookbehind alternation at every position) cost 1.57 s on 255k words, the anchored form 0.10 s. Proclitics carrying their own tashkeel (وَ) are not covered yet.
- D-24 Start-up is gated: `nis serve` = migrate → `nis doctor` → serve; blockers stop the start (override `--skip-doctor`). The container CMD uses it. Doctor/verify output never contains manuscript text, keys or passwords.
- D-25 Compose backups run inside the containers (pg_dump in `db`, object store from `api`) so the host needs only Docker; verification restores into a scratch database and writes `VERIFIED`, which `nis doctor` reads through a read-only `/backups` mount.
- D-26 Single-user key lives in `~/.config/kateb/master.key` (mode 600), outside the data folder, so a copied data folder or backup alone cannot be read.
- D-27 A failing skill no longer fails the run: its writes are rolled back, the step is marked failed with an author-safe message, the run continues and ends `partial`. Retry re-queues only non-done steps (checkpoint) and re-checks external consent; earlier failures are kept in `output.history` and counted in operator metrics. Tracebacks never reach the panel.
- D-28 «مسار الرواية» is computed, never stored: stage states come from counts and timestamps (last edit vs last full check vs last export), so the path cannot drift from the manuscript. The next step follows editorial priority (high conflicts → pending decisions → stale analysis → foundation → bible → sources → writing → publish) and only offers actions the user's role allows.
- D-29 Provider transport: up to 3 attempts for transient failures (408/409/429/5xx/529/network/timeout) with exponential backoff honouring Retry-After ≤ 20 s; permanent failures stop at once. No built-in model name — the operator sets NIS_LLM_MODEL (doctor and the adapter both require it). Tokens are metered per run as input/output separately (`Metered`), so cost uses the two prices correctly. `nis provider-check --send-test-prompt` sends only a fixed sentence.
- D-30 Recommended multi-device model is one server, many browsers. `--lan` exposes it only after the owner account exists and with registration forced closed (the first account becomes administrator, so registration must never be open to a network).
- D-31 Archive import keeps IDs when the project does not exist on this server (same novel on another computer keeps one identity) and forks with fresh IDs when it does (unchanged behaviour on the same server).
- D-32 Archive merge never overwrites: revisions are append-only; a unit's text fast-forwards only along its own revision ancestry; divergent heads are kept in history labelled «من جهاز آخر» for a human choice; other records are last-modified-wins by updated_at. A SQLite database in a sync folder is a doctor blocker.
