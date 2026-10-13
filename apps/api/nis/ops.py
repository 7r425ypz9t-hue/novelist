"""Operator checks: `nis doctor` (is this installation ready to serve?) and `nis verify-data` (is the data whole?).

Both are read-only. They never print manuscript content, keys or passwords — only counts and verdicts, so their
output can be pasted into a support ticket.
"""

from __future__ import annotations

import os
import shutil
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

OK, WARN, FAIL = "ok", "warn", "fail"


@dataclass
class Check:
    key: str
    status: str
    title: str
    detail: str = ""


def _check_python() -> Check:
    v = sys.version_info
    ok = v >= (3, 11)
    return Check("python", OK if ok else FAIL, "إصدار بايثون", f"{v.major}.{v.minor}.{v.micro}" + ("" if ok else " — المطلوب 3.11 فأحدث"))


def _check_database() -> list[Check]:
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory
    from sqlalchemy import text

    from .cli import _alembic_cfg
    from .config import get_settings
    from .db import get_engine

    s = get_settings()
    engine_name = "SQLite" if s.is_sqlite else "PostgreSQL"
    try:
        t0 = time.perf_counter()
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
            ms = (time.perf_counter() - t0) * 1000
            current = MigrationContext.configure(conn).get_current_revision()
    except Exception as e:  # noqa: BLE001 — report any driver/network error as a failed check
        return [Check("database", FAIL, "قاعدة البيانات", f"{engine_name}: تعذّر الاتصال ({type(e).__name__})")]
    out = [Check("database", OK, "قاعدة البيانات", f"{engine_name} · {ms:.0f} ms")]
    head = ScriptDirectory.from_config(_alembic_cfg()).get_current_head()
    if current == head:
        out.append(Check("migrations", OK, "ترحيلات المخطط", f"محدّث ({head})"))
    else:
        out.append(Check("migrations", WARN, "ترحيلات المخطط",
                         f"الحالي {current or 'لا شيء'} والمطلوب {head} — نفّذ `nis migrate` (يُنفَّذ تلقائياً عند `nis serve`)"))
    if s.is_sqlite and not s.database_url.startswith("sqlite:///:memory:"):
        out.append(Check("engine", OK, "محرّك التخزين", "SQLite مناسب لكاتب واحد على جهازه؛ للخادم المشترك استعمل PostgreSQL"))
    return out


def _check_storage() -> list[Check]:
    from .config import get_settings

    d = Path(get_settings().data_dir)
    try:
        d.mkdir(parents=True, exist_ok=True)
        probe = d / ".doctor-probe"
        probe.write_text("ok")
        probe.unlink()
    except OSError as e:
        return [Check("storage", FAIL, "مجلد البيانات", f"{d}: غير قابل للكتابة ({e.strerror})")]
    free_gb = shutil.disk_usage(d).free / 1e9
    status = OK if free_gb >= 2 else WARN if free_gb >= 0.5 else FAIL
    return [Check("storage", OK, "مجلد البيانات", f"{d} قابل للكتابة"),
            Check("disk", status, "المساحة الحرة", f"{free_gb:.1f} GB" + ("" if status == OK else " — أفرغ مساحة قبل التصدير والنسخ"))]


def _check_encryption() -> Check:
    from sqlalchemy import text

    from . import crypto
    from .db import get_engine

    try:
        on = crypto.enabled()
    except Exception:  # noqa: BLE001 — malformed key
        return Check("encryption", FAIL, "التشفير أثناء التخزين", "NIS_MASTER_KEY غير صالح (يجب 32 بايت بترميز base64) — أنشئ مفتاحاً بـ `nis new-key`")
    with get_engine().connect() as conn:
        sealed = conn.execute(text("SELECT text_plain FROM documents WHERE text_plain LIKE 'enc:v1:%' LIMIT 1")).scalar()
        plain = conn.execute(text("SELECT count(*) FROM documents WHERE text_plain NOT LIKE 'enc:v1:%' AND text_plain <> ''")).scalar() or 0
    if not on:
        if sealed:
            return Check("encryption", FAIL, "التشفير أثناء التخزين", "في القاعدة محتوى مشفّر ولم يُضبط NIS_MASTER_KEY — لن تُقرأ المخطوطات")
        return Check("encryption", WARN, "التشفير أثناء التخزين", "غير مفعّل — اضبط NIS_MASTER_KEY ثم `nis encrypt-existing`")
    if sealed:
        try:
            crypto.open_(sealed)
        except Exception:  # noqa: BLE001 — wrong key / tampered row
            return Check("encryption", FAIL, "التشفير أثناء التخزين", "المفتاح الحالي لا يفتح المحتوى المخزَّن — ليس هو المفتاح الذي شُفّر به")
    detail = "مفعّل، والمفتاح يفتح المحتوى المخزَّن" if sealed else "مفعّل"
    if plain:
        return Check("encryption", WARN, "التشفير أثناء التخزين", f"{detail}؛ مستندات غير مشفّرة: {plain} — نفّذ `nis encrypt-existing`")
    return Check("encryption", OK, "التشفير أثناء التخزين", detail)


def _check_panel() -> Check:
    idx = Path(__file__).resolve().parent / "static" / "index.html"
    if idx.exists():
        return Check("panel", OK, "لوحة التحكم المبنية", "موجودة ويخدمها الخادم")
    return Check("panel", WARN, "لوحة التحكم المبنية", "غير مبنية — `cd apps/web && npm ci && npx vite build` (أو استعمل الحاوية)")


def _check_exports() -> list[Check]:
    fonts = Path(__file__).resolve().parent / "assets" / "fonts"
    have = all((fonts / f).exists() for f in ("Amiri-Regular.ttf", "Amiri-Bold.ttf", "OFL.txt"))
    out = [Check("fonts", OK if have else FAIL, "خط الكتب المصدَّرة", "Amiri (OFL) مضمَّن" if have else "ملفات Amiri ناقصة من nis/assets/fonts")]
    try:
        import weasyprint  # noqa: F401

        out.append(Check("pdf", OK, "محرّك PDF", "WeasyPrint (HarfBuzz): تشكيل كامل وحواشٍ في الصفحة"))
    except Exception:  # noqa: BLE001 — missing wheel or missing Pango system libraries
        out.append(Check("pdf", WARN, "محرّك PDF", "المحرّك الاحتياطي ReportLab: يعمل، لكن التشكيل الكامل يحتاج WeasyPrint ومكتبات Pango"))
    return out


def _check_provider() -> Check:
    from .config import get_settings

    s = get_settings()
    p = s.llm_provider
    if p == "disabled":
        return Check("provider", OK, "مزوّد النماذج", "معطّل — الكتابة والتحليل الحتمي والبحث تعمل كاملة")
    if p == "anthropic":
        if not s.llm_api_key or not s.llm_model:
            return Check("provider", FAIL, "مزوّد النماذج", "anthropic يتطلب NIS_LLM_API_KEY وNIS_LLM_MODEL")
        return Check("provider", OK, "مزوّد النماذج", f"anthropic · {s.llm_model} (خارجي: موافقة المشروع + إقرار كل تشغيل)")
    if p == "openai_compatible":
        if not s.llm_base_url or not s.llm_model:
            return Check("provider", FAIL, "مزوّد النماذج", "openai_compatible يتطلب NIS_LLM_BASE_URL وNIS_LLM_MODEL")
        from .agents.providers import get_provider

        where = "محلي" if not get_provider().describe().get("external", True) else "خارجي: موافقة المشروع + إقرار كل تشغيل"
        return Check("provider", OK, "مزوّد النماذج", f"openai_compatible · {s.llm_model} ({where})")
    return Check("provider", FAIL, "مزوّد النماذج", f"قيمة غير معروفة: {p}")


def _check_accounts() -> list[Check]:
    from sqlalchemy import func, select

    from .config import get_settings
    from .db import SessionLocal
    from .models import User

    s = get_settings()
    with SessionLocal() as db:
        users = db.scalar(select(func.count()).select_from(User)) or 0
        admins = db.scalar(select(func.count()).select_from(User).where(User.is_admin.is_(True))) or 0
    out = []
    if users == 0:
        out.append(Check("accounts", WARN, "الحسابات", "لا حسابات بعد — أول من يسجّل يصبح مسؤولاً" if s.first_user_is_admin
                         else "لا حسابات بعد — أنشئ مسؤولاً بـ `nis create-admin`"))
    elif admins == 0:
        out.append(Check("accounts", WARN, "الحسابات", f"{users} · لا مسؤول بينها — `nis create-admin you@example.com`"))
    else:
        out.append(Check("accounts", OK, "الحسابات", f"{users} · المسؤولون: {admins}"))
    if s.allow_registration and users > 0 and not s.is_sqlite:
        out.append(Check("registration", WARN, "التسجيل المفتوح", "مفتوح على خادم مشترك — أغلقه بـ NIS_ALLOW_REGISTRATION=false بعد إنشاء الحسابات"))
    return out


def _check_backups() -> Check:
    root = os.environ.get("NIS_BACKUP_DIR", "").strip()
    if not root:
        return Check("backups", WARN, "النسخ الاحتياطي", "NIS_BACKUP_DIR غير مضبوط — لا يمكن التحقق من عمر آخر نسخة")
    sets = sorted(Path(root).glob("nis-*/MANIFEST.sha256"))
    if not sets:
        return Check("backups", FAIL, "النسخ الاحتياطي", f"لا نسخ في {root}")
    newest = sets[-1].parent
    age_h = (time.time() - sets[-1].stat().st_mtime) / 3600
    verified = (newest / "VERIFIED").exists()
    status = OK if age_h <= 26 and verified else WARN if age_h <= 72 else FAIL
    return Check("backups", status, "النسخ الاحتياطي",
                 f"آخر نسخة {newest.name} قبل {age_h:.0f} ساعة — " + ("تحقّق استرجاعها" if verified else "لم يُتحقّق استرجاعها بعد"))


def doctor() -> list[Check]:
    checks = [_check_python()]
    db = _check_database()
    checks += db
    reachable = db[0].status != FAIL
    checks += _check_storage()
    if reachable:
        checks.append(_check_encryption())
    checks.append(_check_panel())
    checks += _check_exports()
    checks.append(_check_provider())
    if reachable:
        checks += _check_accounts()
    checks.append(_check_backups())
    return checks


def print_doctor(checks: list[Check], as_json: bool = False) -> int:
    if as_json:
        import json

        print(json.dumps([asdict(c) for c in checks], ensure_ascii=False, indent=1))
    else:
        mark = {OK: "✔", WARN: "!", FAIL: "✘"}
        for c in checks:
            print(f" {mark[c.status]}  {c.title}: {c.detail}")
        fails = sum(c.status == FAIL for c in checks)
        warns = sum(c.status == WARN for c in checks)
        print(f"\n{'جاهز للتشغيل' if not fails else 'غير جاهز للتشغيل'} — العوائق: {fails} · التنبيهات: {warns}")
    return 1 if any(c.status == FAIL for c in checks) else 0


def verify_data() -> dict:
    """Every revision matches its checksum; every source file object exists; encrypted rows open with this key."""
    from sqlalchemy import func, select

    from .cli import migrate
    from .db import SessionLocal
    from .models import Document, Project, Revision, SourceFile
    from .services.manuscript import canonical_hash
    from .storage import store

    migrate()
    unreadable = bad = 0
    with SessionLocal() as db:
        rev_ids = list(db.scalars(select(Revision.id)))
        doc_ids = list(db.scalars(select(Document.id)))
        missing = sum(1 for s in db.scalars(select(SourceFile)) if not (store().root / s.object_key).exists())
        projects = db.scalar(select(func.count()).select_from(Project)) or 0
    # one row per session so a row that will not decrypt is counted, not fatal
    for model, ids in ((Revision, rev_ids), (Document, doc_ids)):
        for i in ids:
            with SessionLocal() as db:
                try:
                    row = db.get(model, i)
                    if model is Revision and canonical_hash(row.content_json) != row.checksum:
                        bad += 1
                    else:
                        _ = row.text_plain
                except Exception:  # noqa: BLE001 — wrong key, missing key or tampered ciphertext
                    unreadable += 1
    return {"projects": projects, "documents": len(doc_ids), "revisions": len(rev_ids),
            "checksum_mismatches": bad, "unreadable_rows": unreadable, "missing_source_files": missing,
            "ok": bad == 0 and missing == 0 and unreadable == 0}
