# Progress

- [x] Architectural specifications reviewed; 27 findings, 23 fully addressed (docs/SPEC_REVIEW.md).
- [x] Phase 0 — monorepo, migrations (Alembic), CI workflow, Docker/compose, auth, storage.
- [x] Phase 1 — projects/parts/chapters/scenes, RTL editor, local journal + If-Match sync, revisions/diff/restore, DOCX export, e2e.
- [x] Phase 2 — characters/places/events/relations/facts, timeline and graph views, rule-based continuity (11 rules) with evidence and waivers.
- [x] Phase 3 — source library (PDF/DOCX/TXT/MD), licensing + consent, project-isolated retrieval, citations, injection screening.
- [x] Phase 4 — A00–A12 + 21 skills, cancellable idempotent runs, proposals with diff and accept/reject/modify, editorial report.
- [x] Phase 5 (partial) — style fingerprint with consent, NLQI human rubric, lexical affect/reading simulation (labelled hypothetical).
- [x] Phase 6 (partial) — PDF/EPUB, data export/restore, backup + verified restore scripts, admin console, 255k-word performance smoke.
- [x] Tests executed: 60 backend (SQLite and PostgreSQL 16) + 2 opt-in load tests, 6 frontend unit, 4 Playwright e2e incl. axe WCAG audit (Chromium).
- [x] NFR04 load (1,000 scenes / 300 characters) — single-pass name matcher cut the continuity scan from 11.1 s to 2.8 s.
- [x] Demo and test fixtures use neutral original names only.
- [x] Continuity golden set (20 planted errors + 20 clean cases, original text): precision 1.00, recall 1.00 — author-built, so optimistic.
- [x] Hijri calendar for story time (tabular conversion, author wording kept in the label).
- [x] HarfBuzz/Pango PDF (WeasyPrint): full tashkeel, page footnotes, TOC page numbers, bookmarks; ReportLab fallback kept and tested.
- [x] Product renamed «كاتب»; owner palette (#FFFFFF #84DCC6 #A5FFD6 #FFA69E #FF686B) in light (default) and dark themes, axe-clean.
- [x] Local search expansion: morphology, curated synonyms, Story Bible aliases — transparent, synonyms never evidence alone.
- [x] Fictional-world calendars per project (months, epoch, ratio) alongside Hijri.
- [x] Encryption at rest (AES-256-GCM, server key) for manuscript, revisions, source chunks, comments; `nis encrypt-existing` for legacy rows.
- [x] Typography: Amiri (OFL) across UI and every export; manuscript 14px / line-height 1.5; «سكرتارية التحرير» dashboard with fixed motto.
- [x] Arabic-aware find & replace (tashkeel/tatweel, hamza/taa/alef-maqsura/digit forms, whole word) in the unit and read-only across the manuscript with jump-to-hit; whole word accepts attached proclitics (و، ف، ب، ك، ل، ال). Manuscript-wide search on 255,000 words: 0.19 s (`NIS_PERF_FULL=1`).

- [x] Operations: `nis doctor` readiness check (runs before every `nis serve`, refuses to start on a blocker such as a key that does not open stored content), `nis verify-data`, `create-admin --password-stdin`, `scripts/start.sh` (single user, key generated outside the data folder), `.dockerignore`, mirror-able base images.
- [x] Docker verified in a real daemon: image built (apt step skipped, see open items), runs as uid 10001, compose with PostgreSQL 16 healthy, content encrypted in PostgreSQL, data survives restart, wrong key → container refuses to serve.
- [x] Compose backups without host tools (`compose-backup.sh` with retention, `compose-verify.sh` restoring into a scratch database), daily systemd timer; tampered backup rejected.

- [x] Agent operations: per-step failure isolation (rollback of the failed step only, run ends «partial»), author-safe Arabic errors (tracebacks to the server log with the run id), step durations and live progress, retry from checkpoint with attempt history, `/v1/admin/agents` per-skill failure rate / avg / p95 and stalled runs.

- [x] «مسار الرواية» on the editorial secretariat page: eight stages (foundation → bible → writing → analysis → continuity → decisions → sources → publish) computed from live data, one recommended next step by editorial priority, role-aware actions (`GET /v1/projects/{id}/workflow`).

- [x] Provider path: bounded retries with backoff and Retry-After, fast Arabic failures for 401/403/404/4xx, no built-in model name, configurable Anthropic base URL (gateways), per-run input/output token metering and exact cost when prices are set, `nis provider-check [--send-test-prompt]` (fixed prompt, never manuscript text).

- [x] Multi-device: `scripts/start.sh --lan` (refuses without an account, closes registration, prints addresses; doctor fails on open registration), «أجهزتي» (list/revoke sessions, sign out everywhere else; migration 0004), doctor blocks a SQLite database inside a sync folder, stable project identity across computers and `POST /projects/{id}/data-merge` (append-only history, fast-forward text, diverged versions kept in history; idempotent; other novels refused).

Open items (TODO, not done):
- [ ] Docker: the apt step (Pango/HarfBuzz for WeasyPrint) not executed here — deb.debian.org is blocked by this environment's egress policy; everything else built and ran (see below).
- [ ] Firefox/Edge e2e configured in the CI matrix but not yet executed (only Chromium exists here); manual screen-reader review.
- [ ] Embedding-based retrieval (deferred by the owner until infrastructure allows); continuity benchmark on third-party licensed chapters.
- [ ] Human editorial calibration for AT19 and NLQI inter-rater agreement.
- [ ] Successful live model call: needs an operator key (none in this environment). Verified so far: the real network path to api.anthropic.com up to authentication (HTTP 401 with a deliberately invalid key, mapped to an Arabic message); full wire-format runs against a local Anthropic/OpenAI-compatible stand-in, including external-destination gating. Hugging Face and GitHub releases are blocked here, so no local model could be installed.
