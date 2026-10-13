# Progress

- [x] Architectural specifications reviewed; 27 findings, 23 fully addressed (docs/SPEC_REVIEW.md).
- [x] Phase 0 — monorepo, migrations (Alembic), CI workflow, Docker/compose, auth, storage.
- [x] Phase 1 — projects/parts/chapters/scenes, RTL editor, local journal + If-Match sync, revisions/diff/restore, DOCX export, e2e.
- [x] Phase 2 — characters/places/events/relations/facts, timeline and graph views, rule-based continuity (11 rules) with evidence and waivers.
- [x] Phase 3 — source library (PDF/DOCX/TXT/MD), licensing + consent, project-isolated retrieval, citations, injection screening.
- [x] Phase 4 — A00–A12 + 21 skills, cancellable idempotent runs, proposals with diff and accept/reject/modify, editorial report.
- [x] Phase 5 (partial) — style fingerprint with consent, NLQI human rubric, lexical affect/reading simulation (labelled hypothetical).
- [x] Phase 6 (partial) — PDF/EPUB, data export/restore, backup + verified restore scripts, admin console, 255k-word performance smoke.
- [x] Tests executed: 60 backend (SQLite and PostgreSQL 16), 6 frontend unit, 3 Playwright e2e (Chromium).

Open items (TODO, not done):
- [ ] Docker image build not executed in this environment (no Docker daemon); compose file is untested.
- [ ] Cross-browser RTL e2e (Firefox, Edge); automated accessibility audit (axe).
- [ ] NFR04 load with 1,000 scenes / 300 characters.
- [ ] Envelope encryption for private projects; Hijri/fictional calendars; HarfBuzz-based PDF with full tashkeel.
- [ ] Embedding-based hybrid retrieval after a recall benchmark; golden continuity dataset (precision/recall).
- [ ] Human editorial calibration for AT19 and NLQI inter-rater agreement.
- [ ] Live call against a real model provider (adapter implemented, consent flow tested, no network call made).
