# مصفوفة التتبع — المتطلبات ← المكوّن ← ملف التنفيذ ← الاختبار

الحالة: **✅ منفّذ ومختبَر آلياً** · **🟡 منفّذ جزئياً / مختبَر يدوياً** · **⬜ غير منفّذ (TODO)**
مسارات الاختبار: `api/…` = `apps/api/tests/…` · `e2e/…` = `apps/web/e2e/studio.spec.ts` · `web/…` = `apps/web/src/**/*.test.ts`

## المتطلبات الوظيفية

| المعرف | المتطلب | التنفيذ | الاختبار | الحالة |
|---|---|---|---|---|
| FR01 | حسابات، جلسات، أدوار على مستوى المشروع | `nis/routers/auth.py`, `nis/deps.py` (ROLE_PERMISSIONS), `security.py` | `api/test_security.py::test_roles_*`, e2e AT01 | ✅ |
| FR02 | مشروع بعدة روايات، لغة، نوع، وصف، نمط ظهور | `routers/projects.py` (projects, manuscripts) | `api/test_manuscript.py::test_AT01_*` | ✅ |
| FR03 | أجزاء ← فصول ← مشاهد، نقل وإعادة ترقيم بمعرفات ثابتة | `services/manuscript.py` (create_node, move_node, labels) | `api/test_manuscript.py::test_reorder_keeps_ids_and_trash_restore` | ✅ |
| FR04 | محرر RTL، حواشٍ، بحث واستبدال، عداد عربي، لغات مختلطة | `web/src/pages/Write.tsx` (Tiptap + textDirection + Footnote), `text.py`, `lib/arabic.ts` | `api/test_text.py`, `web/lib/arabic.test.ts`, e2e AT01/AT02 | ✅ (التشكيل الاختياري يُكتب يدوياً؛ لا أداة تشكيل آلي) |
| FR05 | حفظ تلقائي، حالة مزامنة ظاهرة، لا فقد عند الانقطاع | `web/src/lib/autosave.ts`, `lib/offline.ts` | e2e AT03, `api/test_manuscript.py::test_AT03_*` | ✅ |
| FR06 | إصدارات ثابتة، فروق، استعادة، منع الكتابة فوق السابق | `models.Revision` (+ ORM guard), `save_document`, `/diff`, `/restore`, حذف ناعم | `api/test_manuscript.py::test_AT04_*`, `test_AT05_*`, `test_revisions_are_immutable_*` | ✅ |
| FR07 | ملفات الشخصيات | `routers/bible.py`, `pages/Bible.tsx` | `api/test_continuity.py` | ✅ (العمر عبر الزمن مشتق من سنة الميلاد) |
| FR08 | الأماكن، إحداثيات اختيارية، قيود تاريخية | `routers/bible.py` | واجهة + `api/test_agents.py` (SK04 ضمن A00) | 🟡 لا خريطة جغرافية |
| FR09 | أحداث بزمن القصة وترتيب السرد، مجهول/نطاق/احتمال، والتقويم الهجري | `models.Event`, `/timeline`, `calendars.py`, `components/HijriPicker.tsx` | `api/test_continuity.py::test_AT08_*`, `api/test_calendars.py`, e2e R4 | ✅ |
| FR10 | مصفوفة المشاهد | `nodes.meta`, `Write.tsx::SceneMatrix`, SK02/SK10 | `api/test_agents.py` | ✅ |
| FR11 | لوحة علاقات وروابط أدلة قابلة للنقر | `/graph`, `pages/Views.tsx::GraphPage`, `EvidenceList` (افتح الشاهد) | يدوي (لقطات) | 🟡 |
| FR12 | بدائل عند الطلب فقط | SK01 (مقترحات `note`)، لا توليد عند فتح الفصل | `api/test_agents.py::test_AT14_*` | ✅ (التوليد يتطلب مزوداً) |
| FR13 | canon / draft / hypothesis / external | `models.CanonFact`, `/facts/{id}/approve` | `api/test_continuity.py::test_canon_requires_author_approval` | ✅ |
| FR14 | تعارضات بشواهد ورفض وإعفاء مسبب | `services/continuity.py` (11 قاعدة), `/conflicts/*/resolve` | `api/test_continuity.py` (B, AT08, AT09, AT22) + `test_continuity_benchmark.py` (40 حالة: دقة 1.00، استدعاء 1.00) | ✅ |
| FR15 | بحث في المرفقات بعد الموافقة والحقوق، استشهاد بالصفحة/المقطع | `services/research.py`, `routers/research.py` | `api/test_research.py` | ✅ |
| FR16 | تقرير تحريري منفصل لا يخلط الوقائع بالذوق | `orchestrator.editorial_report` | `api/test_agents.py::test_AT19_*` | ✅ |
| FR17 | Diff بمبرر وقبول/رفض/تعديل | `services/proposals.py`, `pages/Proposals.tsx` | `api/test_agents.py::test_lint_patches_*`, e2e AT06 | ✅ |
| FR18 | بصمة على عينات مملوكة، قابلة للمحو، لا تقليد | `services/style.py`, `routers/insight.py` | `api/test_insight.py` | ✅ |
| FR19 | سجل لكل تشغيل: السبب، النموذج، التكلفة، المصادر، دون نص خام | `models.AgentRun`, `audit.py` (تنقيح) | `api/test_security.py::test_audit_log_never_stores_manuscript_text` | ✅ (التكلفة تُحسب فقط إن حدّد المشغّل الأسعار) |
| FR20 | DOCX/PDF/EPUB بفهرس وعربية سليمة | `services/exports.py`, `services/pdf_html.py` (HarfBuzz: تشكيل كامل وحواشٍ سفلية) | `api/test_publishing.py::test_AT16_*` + فتح يدوي في LibreOffice | ✅ |
| FR21 | استيراد DOCX/MD/TXT مع معاينة | `/import/preview`, `/import/commit`, `Write.tsx::ImportModal` (معاينة وتحرير العناوين قبل الاعتماد) | `api/test_manuscript.py::test_import_preview_and_commit` | ✅ |
| FR22 | ربط كل دعوى بمصدر أو «غير متحقق» | `models.Citation`, SK13 | `api/test_research.py::test_AT10_*`, `test_AT13_*` | ✅ |
| FR23 | لوحة العمل | `/dashboard`, `pages/Dashboard.tsx` | `api/test_manuscript.py::test_import_*` + لقطات | ✅ |
| FR24 | تصدير/حذف كامل مع إفصاح الاحتفاظ | `services/portability.py`, `DELETE /projects/{id}` | `api/test_publishing.py::test_AT21_AT17_*`, `test_project_deletion_*` | ✅ |
| FR25 | محلي اختياري أو خارجي بإعلان الوجهة | `agents/providers.py` (disabled / anthropic / openai_compatible) | `api/test_agents.py::test_external_provider_is_consent_gated` | ✅ (لم يُستدعَ مزود حقيقي في الاختبارات) |

## المتطلبات غير الوظيفية

| المعرف | الهدف | القياس الفعلي | الحالة |
|---|---|---|---|
| NFR01 | فتح فصل 10k كلمة < 2 ث | 0.015 ث (API، بيئة الاختبار أدناه) | ✅ |
| NFR02 | حفظ محلي ≤ 1 ث | سجل محلي بعد 0.6 ث من التوقف؛ حالة الخادم منفصلة | ✅ |
| NFR03 | لا فقد بعد تعطل المتصفح | e2e: إغلاق التبويب قبل المزامنة ثم الاستعادة | ✅ |
| NFR04 | 150k كلمة، 1000 مشهد، 300 شخصية | 255,000 كلمة/30 فصلاً: فحص استمرارية 2.0 ث، DOCX 2.0 ث · 1,000 مشهد/300 شخصية: فحص استمرارية 2.8 ث، تشغيل A00 الكامل (21 مهارة) 14.5 ث (`test_NFR04_*`) | ✅ |
| NFR05 | عزل البيانات، IDOR، أسرار في البيئة، تشفير التخزين | `deps.py` + اختبار 15 نقطة؛ `crypto.py` (كل الحزمة تعمل مشفّرة) `api/test_crypto.py` | ✅ |
| NFR06 | RTL عبر Chrome/Firefox/Edge | Chromium فقط في هذه البيئة | 🟡 |
| NFR07 | WCAG 2.2 AA | تدقيق axe-core آلي لـ 12 شاشة + الدخول في السمتين: صفر مخالفات خطيرة/حرجة (`e2e/a11y.spec.ts`) | 🟡 آلي فقط؛ التدقيق البشري وقارئ الشاشة لم يُجريا |
| NFR08 | استرجاع النسخ الاحتياطية مجرَّب | `scripts/backup.sh` + `scripts/restore_verify.sh` (SQLite وPostgreSQL) + AT17 | ✅ |
| NFR09 | التوليد قابل للإيقاف ولا يمنع الكتابة | `projects.ai_enabled`, مزود معطّل افتراضياً | `api/test_agents.py::test_disabling_agents_per_project`, `test_AT14_*` ✅ |
| NFR10 | استبدال المزود دون إعادة تصميم | واجهة `Provider` واحدة | ✅ |

**بيئة القياس:** حاوية Linux x86_64، 4 أنوية، Python 3.13، SQLite (WAL)، اختبار عبر TestClient داخل العملية — أرقام توجيهية لا متوسطات إحصائية.

## اختبارات القبول

| AT | المستوى | موضع الاختبار | النتيجة |
|---|---|---|---|
| AT01 | E2E | e2e AT01/AT02 + `api/test_manuscript.py::test_AT01_*` | ✅ |
| AT02 | E2E + visual | e2e (اتجاه محسوب `rtl`) + `api/test_AT02_*` | ✅ Chromium |
| AT03 | E2E | e2e AT03 | ✅ |
| AT04 | Integration | `api/test_AT04_*` | ✅ |
| AT05 | Integration | `api/test_AT05_*` | ✅ |
| AT06 | E2E | e2e AT06 + `api/test_AT06_*` | ✅ |
| AT07 | Integration | `api/test_AT07_*` | ✅ |
| AT08 | E2E | `api/test_AT08_*` (عبر API) | ✅ |
| AT09 | Manual | `api/test_AT09_*` (مؤتمت أيضاً) | ✅ |
| AT10 | Integration | `api/test_AT10_*` | ✅ |
| AT11 | Security | `api/test_AT11_*` | ✅ |
| AT12 | Security | `api/test_AT12_*` | ✅ |
| AT13 | Integration | `api/test_AT13_*` | ✅ |
| AT14 | E2E | `api/test_AT14_*` | ✅ |
| AT15 | Performance | `api/test_platform.py::test_AT15_*`, `test_NFR04_*` (`NIS_PERF_FULL=1`) | ✅ |
| AT16 | E2E + Manual | `api/test_AT16_*` ×3 + فتح DOCX في LibreOffice | ✅ |
| AT17 | DR | `api/test_AT21_AT17_*` + سكربتات النسخ | ✅ |
| AT18 | Security/UX | `api/test_AT18_*` | ✅ |
| AT19 | Human editorial | `api/test_AT19_*` يتحقق من البنية فقط | 🟡 يحتاج محررين بشريين |
| AT20 | Integration | `api/test_AT20_*` | ✅ |
| AT21 | E2E | `api/test_AT21_AT17_*` | ✅ |
| AT22 | Integration | `api/test_AT22_*` | ✅ |

**أوامر التشغيل:** `cd apps/api && pytest -q` (60 اختباراً) · `NIS_DATABASE_URL=postgresql+psycopg://… pytest -q` · `cd apps/web && npm test && npx playwright test` (4 سيناريوهات منها تدقيق الوصول).
