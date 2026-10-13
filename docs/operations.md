# دليل التشغيل والإدارة — كاتب

## 0. اختر طريقة التشغيل

| الحالة | الطريقة | قاعدة البيانات | الأمر |
|---|---|---|---|
| كاتب واحد على جهازه | عملية واحدة بلا Docker | SQLite في `./var` | `scripts/start.sh` |
| خادم لعدة كتّاب أو فريق تحرير | حاويتان (التطبيق + PostgreSQL) | PostgreSQL 16 | `docker compose … up -d` |
| تطوير الواجهة | خادم + Vite بإعادة تحميل حيّة | SQLite | `scripts/dev.sh --demo` |

كل الطرق تمر بالخطوات نفسها عند الإقلاع: **ترحيل المخطط ← فحص الجاهزية (`nis doctor`) ← الخدمة**. فإن وجد الفحص عائقاً (كمفتاح تشفير لا يفتح المحتوى المخزَّن) رفض الخادم البدء وطبع السبب بالعربية، بدلاً من أن يعمل ويعرض مخطوطات لا تُقرأ.

## 1. على جهاز الكاتب (أمر واحد)

```bash
scripts/start.sh                 # http://127.0.0.1:8000
PORT=8080 scripts/start.sh       # منفذ آخر
KATEB_HOME=~/Kateb scripts/start.sh   # نقل مجلد البيانات
```
في أول تشغيل: ينشئ بيئة بايثون، ويثبّت الخادم، ويبني لوحة التحكم (يحتاج Node.js مرة واحدة)، و**يولّد مفتاح التشفير** في `~/.config/kateb/master.key` بصلاحية 600 خارج مجلد البيانات، ثم يشفّر أي محتوى قديم ويبدأ. **احفظ نسخة من ملف المفتاح في مكان آمن منفصل**: من دونه لا تُقرأ المخطوطات حتى من النسخ الاحتياطية.

## 2. على خادم (Docker Compose + PostgreSQL)

```bash
cp .env.example .env                       # اضبط NIS_DB_PASSWORD
docker compose -f infra/docker-compose.yml run --rm --no-deps api python -m nis.cli new-key   # الصق الناتج في NIS_MASTER_KEY
docker compose -f infra/docker-compose.yml --env-file .env up -d --build
echo 'كلمة-مرور-طويلة' | docker compose -f infra/docker-compose.yml --env-file .env exec -T api \
     python -m nis.cli create-admin you@example.com --password-stdin
docker compose -f infra/docker-compose.yml --env-file .env exec api python -m nis.cli doctor
```
- الحاوية تعمل بمستخدم غير جذري (uid 10001)، والمنفذ مربوط بـ `127.0.0.1`؛ ضع أمامها وكيل TLS (Caddy أو Nginx).
- بعد إنشاء الحسابات أغلق التسجيل: `NIS_ALLOW_REGISTRATION=false` ثم `up -d`.
- حدّ المعدّل في الذاكرة يكفي لنسخة واحدة؛ مع عدة نسخ ضع حدّاً مشتركاً في الوكيل العكسي.
- **إن رفض Docker Hub السحب (429 Too Many Requests)** فابنِ من مرآة رسمية دون تعديل الملف:
  ```bash
  docker compose … build --build-arg NODE_IMAGE=mirror.gcr.io/library/node:22-bookworm-slim \
                        --build-arg PYTHON_IMAGE=mirror.gcr.io/library/python:3.12-slim-bookworm
  ```
- `.dockerignore` يمنع دخول `var/` وقواعد البيانات المحلية و`.env` و`node_modules` إلى سياق البناء، فلا تتسرّب مخطوطة محلية إلى الصورة.

## 3. فحص الجاهزية: `nis doctor`

يقرأ ولا يكتب، ولا يطبع نصاً من المخطوطات ولا مفتاحاً ولا كلمة مرور؛ فيصلح لصقه في طلب دعم. `--json` لأدوات المراقبة. رمز الخروج 1 عند وجود عائق.

| الفحص | عائق ✘ عندما | تنبيه ! عندما | العلاج |
|---|---|---|---|
| قاعدة البيانات | تعذّر الاتصال | — | تحقّق من `NIS_DATABASE_URL` وتشغيل PostgreSQL |
| ترحيلات المخطط | — | المخطط أقدم من الشيفرة | `nis migrate` (يُنفَّذ تلقائياً عند الإقلاع) |
| مجلد البيانات والمساحة | غير قابل للكتابة أو أقل من 0.5 GB | أقل من 2 GB | صلاحيات المجلد أو تفريغ مساحة |
| التشفير أثناء التخزين | مفتاح غير صالح، أو مفتاح لا يفتح المخزَّن، أو محتوى مشفّر بلا مفتاح | التشفير غير مفعّل، أو بقيت مستندات غير مشفّرة | المفتاح الصحيح، ثم `nis encrypt-existing` |
| لوحة التحكم | — | غير مبنية | `npx vite build` أو استعمل الحاوية |
| خط الكتب المصدَّرة | ملفات Amiri ناقصة | — | أعد التثبيت |
| محرّك PDF | — | المحرّك الاحتياطي (ReportLab) | ثبّت مكتبات Pango (موجودة في الحاوية الرسمية) |
| مزوّد النماذج | إعداد ناقص (مفتاح أو نموذج أو عنوان) | — | انظر §6 |
| الحسابات والتسجيل | — | لا مسؤول، أو تسجيل مفتوح على خادم مشترك | `create-admin`، و`NIS_ALLOW_REGISTRATION=false` |
| النسخ الاحتياطي | لا نسخ، أو آخر نسخة أقدم من 72 ساعة | لم يُتحقّق من آخر نسخة، أو عمرها 26–72 ساعة | §4 |

## 4. النسخ الاحتياطي والاسترجاع (NFR08)

**القاعدة: النسخة لا تُعدّ صالحة قبل أن تُسترجع فعلاً.** لذا لكل طريقة أمر نسخ وأمر تحقّق، والتحقّق يكتب ملف `VERIFIED` يقرؤه `nis doctor`.

### خادم Docker Compose (لا يحتاج أدوات على المضيف)
```bash
scripts/compose-backup.sh /srv/kateb-backups          # pg_dump داخل حاوية القاعدة + ملفات المصادر من حاوية التطبيق + بصمات SHA-256
scripts/compose-verify.sh /srv/kateb-backups/nis-<stamp>
```
`compose-verify.sh` يتحقق من البصمات، ويسترجع إلى **قاعدة مؤقتة** داخل حاوية PostgreSQL ومجلد مؤقت داخل حاوية التطبيق، ويشغّل `nis verify-data` عليهما (بصمة كل مراجعة، ووجود كل ملف مصدر، وفكّ تشفير كل صف بالمفتاح الحالي)، ثم يحذف النسختين المؤقتتين. أي بايت معدَّل في النسخة يُكتشف ويُرفض. يحذف `compose-backup.sh` النسخ الأقدم من `KEEP_DAYS` (افتراضياً 30)، ولا يترك نسخة ناقصة إن فشل في منتصفه.

**الجدولة اليومية** (نسخ ثم تحقّق، 03:17 بتوقيت الخادم):
```bash
sudo cp infra/systemd/kateb-backup.* /etc/systemd/system/    # عدّل المسارات داخل الملف أولاً
sudo systemctl daemon-reload && sudo systemctl enable --now kateb-backup.timer
systemctl list-timers kateb-backup.timer                     # موعد التشغيل القادم
```
اضبط `NIS_BACKUP_HOST_DIR` في `.env` على مجلد النسخ؛ يُركَّب للقراءة فقط في `/backups` داخل الحاوية ليعرض `nis doctor` عمر آخر نسخة وحالة تحقّقها.

### على جهاز الكاتب أو خادم بلا Docker
```bash
NIS_DATABASE_URL=… NIS_DATA_DIR=… scripts/backup.sh /backups
scripts/restore_verify.sh /backups/nis-<stamp>                                             # SQLite
NIS_RESTORE_PG_URL=postgresql+psycopg://…/scratch scripts/restore_verify.sh /backups/nis-<stamp>   # PostgreSQL
```

### على مستوى المشروع
«الإعدادات ← تنزيل الأرشيف» يُنتج ZIP ذاتي الوصف ببصمات SHA-256، ويُستعاد بـ«استعادة أرشيف» إلى مشروع جديد بعد التحقق من سلامته.

## 5. مفتاح التشفير

```bash
nis new-key                    # 32 بايت عشوائية بترميز base64
nis encrypt-existing           # يشفّر الصفوف القديمة؛ آمن للتكرار
```
يُشفَّر نص المخطوط والمراجعات ومقاطع المصادر والتعليقات بـ AES-256-GCM. **حدود الحماية:** يحمي ملفات قاعدة البيانات والنسخ الاحتياطية المسرّبة، ولا يخفي المحتوى عمّن يتحكم بالخادم العامل وبيئته. **فقدان المفتاح يعني فقدان المحتوى المشفّر**؛ فاحفظه في مدير أسرار، منفصلاً عن النسخ الاحتياطية. والتحقق من النسخ يحتاج المفتاح نفسه.

## 6. مزوّد النماذج (اختياري)

| القيمة | الوجهة | ملاحظات |
|---|---|---|
| `disabled` (افتراضي) | لا شيء | كل الكتابة والتحليل الحتمي والبحث تعمل |
| `openai_compatible` + `NIS_LLM_BASE_URL=http://127.0.0.1:11434/v1` | خادم محلي (Ollama أو LM Studio) | يُعدّ محلياً إن كان العنوان localhost |
| `anthropic` + `NIS_LLM_API_KEY` | api.anthropic.com | خارجي: موافقة المشروع + إقرار كل تشغيل + تأكيد المخاطرة العالية |

الأسعار لا تُفترض: لعرض تكلفة تقديرية اضبط `NIS_LLM_PRICE_IN_PER_MTOK` و`NIS_LLM_PRICE_OUT_PER_MTOK`. راجع سياسة الاحتفاظ والتدريب لدى المزوّد وسجّلها قبل منح الموافقة.

## 7. سياسة الاحتفاظ والحذف

- حذف المشروع (بتأكيد العنوان حرفياً) يحذف فوراً: المخطوط، والمراجعات، والمصادر وملفاتها، والمقاطع المفهرسة، والتصديرات، والمقترحات، والبصمة.
- تبقى نسخ في النسخ الاحتياطية حتى انتهاء دورة الاحتفاظ (`KEEP_DAYS`، الموصى به 30 يوماً)، ويُعلَن ذلك للمستخدم في رسالة الحذف.
- محو البصمة الأسلوبية يصفّر خصائصها ويُلغي موافقتها؛ ولا يُخزَّن نص العينات أصلاً.

## 8. الترقية

```bash
scripts/compose-backup.sh /srv/kateb-backups && scripts/compose-verify.sh "$(ls -d /srv/kateb-backups/nis-* | tail -1)"
git pull && docker compose -f infra/docker-compose.yml --env-file .env up -d --build    # الترحيل يجري عند الإقلاع
```
بلا Docker: `git pull && pip install -e apps/api && nis migrate`. لإضافة ترحيل: عدّل `nis/models.py` ثم `alembic revision --autogenerate -m "…"`؛ واختبار `test_migrations_are_in_sync_with_models` يمنع نسيانه.

## 9. المراقبة

- لوحة المسؤول (`/admin`): صحة الخدمة وزمن قاعدة البيانات، وقابلية الكتابة في التخزين، والمزوّد، والتشغيلات النشطة، والقياسات، والمستخدمون، وسجل تدقيق منقّح.
- `nis doctor --json` لأدوات المراقبة الخارجية؛ و`/v1/health` لفحص الحياة (تستعمله الحاوية).
- كل استجابة تحمل `X-Request-ID` للربط بسجلات الخادم.

## 10. استكشاف الأعطال

| العَرَض | السبب المرجّح | الإجراء |
|---|---|---|
| الحاوية تُعاد تشغيلها والسجل يقول «لن يبدأ الخادم…» | عائق في `nis doctor` (غالباً المفتاح) | `docker compose logs api` ثم عالج السطر الموسوم ✘ |
| «المفتاح الحالي لا يفتح المحتوى المخزَّن» | تغيّر `NIS_MASTER_KEY` | أعد المفتاح الأصلي؛ لا تشغّل `encrypt-existing` بمفتاح جديد |
| PDF بلا تشكيل كامل | لا مكتبات Pango (المحرّك الاحتياطي) | استعمل الحاوية الرسمية أو ثبّت `libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b` |
| `429 Too Many Requests` عند البناء | حدّ Docker Hub | مرآة `mirror.gcr.io` (§2) |
| `compose-verify.sh` يفشل في `sha256sum` | النسخة تالفة أو عُدّلت | لا تعتمدها؛ خذ نسخة جديدة وتحقّق منها |
