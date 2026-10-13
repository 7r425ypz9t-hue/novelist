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
- [x] Encryption at rest (AES-256-GCM, server key) for manuscript, revisions, source chunks, comments; `nis encrypt-existing` for legacy rows.

Open items (TODO, not done):
- [ ] Docker image build not executed in this environment (no Docker daemon); compose file is untested.
- [ ] Cross-browser RTL e2e (Firefox, Edge); manual screen-reader review (automated axe audit passes).
- [ ] Per-project keys derived from an author secret (operator-blind); fictional-world calendars.
- [ ] Embedding-based hybrid retrieval after a recall benchmark; continuity benchmark on third-party licensed chapters.
- [ ] Human editorial calibration for AT19 and NLQI inter-rater agreement.
- [ ] Live call against a real model provider (adapter implemented, consent flow tested, no network call made).
