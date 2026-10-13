# دليل التشغيل والإدارة

## 1. التشغيل المحلي (مستخدم واحد، SQLite)

```bash
scripts/dev.sh --demo      # API على :8000 + واجهة Vite على :5173 مع مشروع تجريبي أصلي
```
الدخول التجريبي: `demo@nis.local` / `demo-password-2026` (حساب محلي للعرض فقط).

بديل بعملية واحدة (الواجهة مبنية ويخدمها الخادم):
```bash
cd apps/web && npm ci && npx vite build          # يكتب إلى apps/api/nis/static
cd ../api && pip install -e . && nis serve        # http://127.0.0.1:8000
```

## 2. النشر على خادم (PostgreSQL)

```bash
cp .env.example .env        # اضبط NIS_DB_PASSWORD
docker compose -f infra/docker-compose.yml --env-file .env up -d --build
docker compose -f infra/docker-compose.yml exec api python -m nis.cli create-admin you@example.com
```
- ضع الخدمة خلف وكيل TLS (Caddy/Nginx). المنفذ مربوط بـ `127.0.0.1` افتراضياً.
- أول حساب يُسجَّل يصبح مسؤولاً (`NIS_FIRST_USER_IS_ADMIN`)؛ أغلق التسجيل بعده بـ `NIS_ALLOW_REGISTRATION=false` إن شئت.
- حدّ المعدّل في الذاكرة يكفي لعملية واحدة؛ مع عدة نسخ ضع حدّاً مشتركاً في الوكيل العكسي.

## 3. مزود النماذج (اختياري)

| القيمة | الوجهة | ملاحظات |
|---|---|---|
| `disabled` (افتراضي) | لا شيء | كل الكتابة والتحليل الحتمي والبحث يعمل |
| `openai_compatible` + `NIS_LLM_BASE_URL=http://127.0.0.1:11434/v1` | خادم محلي (Ollama/LM Studio) | يُعدّ محلياً إن كان العنوان localhost |
| `anthropic` + `NIS_LLM_API_KEY` | api.anthropic.com | خارجي: يتطلب موافقة المشروع + إقرار التشغيل + تأكيد مخاطرة عالية |

الأسعار لا تُفترض: لعرض تكلفة تقديرية اضبط `NIS_LLM_PRICE_IN_PER_MTOK` و`NIS_LLM_PRICE_OUT_PER_MTOK`. راجع سياسة الاحتفاظ والتدريب لدى المزود وسجّلها قبل منح الموافقة.

## 4. النسخ الاحتياطي والاسترجاع (NFR08)

```bash
NIS_DATABASE_URL=… NIS_DATA_DIR=… scripts/backup.sh /backups
scripts/restore_verify.sh /backups/nis-<stamp>                       # SQLite
NIS_RESTORE_PG_URL=postgresql+psycopg://…/scratch scripts/restore_verify.sh /backups/nis-<stamp>
```
`restore_verify.sh` يتحقق من بصمات الملفات، ويسترجع إلى موقع مؤقت، ويطبّق الترحيلات، ويعيد حساب بصمة **كل مراجعة**، ويتأكد من وجود كل ملف مصدر؛ ويخرج بخطأ عند أي نقص. **النسخة لا تُعدّ صالحة قبل نجاح هذا الأمر.** جدولة مقترحة: نسخ يومي، تحقق أسبوعي، احتفاظ 30 يوماً.

على مستوى المشروع: «الإعدادات ← تنزيل الأرشيف» يُنتج ZIP ذاتي الوصف يُستعاد بـ «استعادة أرشيف» إلى مشروع جديد بعد التحقق من سلامته.

## 5. سياسة الاحتفاظ والحذف

- حذف المشروع (بتأكيد العنوان حرفياً) يحذف فوراً: المخطوط، المراجعات، المصادر وملفاتها، المقاطع المفهرسة، التصديرات، المقترحات، البصمة.
- تبقى نسخٌ في النسخ الاحتياطية حتى انتهاء دورة الاحتفاظ التي يحددها المشغّل (الافتراض الموصى به 30 يوماً) — ويُعلَن ذلك للمستخدم في رسالة الحذف.
- محو البصمة الأسلوبية يصفّر خصائصها ويُلغي موافقتها؛ لا يُخزَّن نص العينات أصلاً.

## 6. الترقية

```bash
git pull && pip install -e apps/api && nis migrate   # ترحيلات Alembic؛ نفّذ backup قبلها
```
لإضافة ترحيل: عدّل `nis/models.py` ثم `alembic revision --autogenerate -m "…"`؛ اختبار `test_migrations_are_in_sync_with_models` يمنع نسيان الترحيل.

## 7. المراقبة

لوحة المسؤول (`/admin`): صحة الخدمة وزمن قاعدة البيانات، قابلية الكتابة في التخزين، المزود، التشغيلات النشطة، القياسات، المستخدمون، وسجل تدقيق منقّح. كل استجابة تحمل `X-Request-ID` للربط بسجلات الخادم.
