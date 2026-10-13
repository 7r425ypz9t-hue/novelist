"""Skill implementations. Each returns a SkillResult; text changes are only ever *proposals*.

Every finding is labelled with `certainty` (supported | inferred | speculative) and `kind`
(objective = verifiable fact about the text; taste = critical preference) so the editorial report never
mixes facts with preferences (FR16).
"""

from __future__ import annotations

import re
import statistics
from collections import Counter, defaultdict
from collections.abc import Callable
from typing import Any

from ..services import continuity
from ..services.style import compare_features, extract_features
from ..text import (
    count_words,
    is_arabic,
    normalize_ar,
    search_tokens,
    sentences,
    strip_diacritics,
    words,
)
from .context import SkillResult, ToolContext
from .providers import Provider, ProviderUnavailable, parse_json_block

SkillFn = Callable[[ToolContext, Provider, dict[str, Any]], SkillResult]
REGISTRY: dict[str, SkillFn] = {}


def skill(sid: str) -> Callable[[SkillFn], SkillFn]:
    def deco(fn: SkillFn) -> SkillFn:
        REGISTRY[sid] = fn
        return fn

    return deco


def ev(scene, start: int | None = None, end: int | None = None, note: str = "") -> dict[str, Any]:
    d: dict[str, Any] = {"kind": "node", "node_id": str(scene.node.id), "document_id": str(scene.doc.id),
                         "label": scene.label}
    if start is not None:
        d.update({"start": start, "end": end, "quote": scene.text[start:end][:240]})
    if note:
        d["note"] = note
    return d


DIALOGUE_LINE = re.compile(r"^\s*[—–-]\s*\S", re.MULTILINE)
QUOTED = re.compile(r"«[^»]{1,600}»|\"[^\"]{1,600}\"|“[^”]{1,600}”")


def dialogue_ratio(text: str) -> float:
    if not text:
        return 0.0
    q = sum(len(m.group(0)) for m in QUOTED.finditer(text))
    dl = sum(len(line) for line in text.split("\n") if DIALOGUE_LINE.match(line))
    return min(1.0, (q + dl) / max(1, len(text)))


def chapter_groups(ctx: ToolContext) -> dict[Any, list]:
    g: dict[Any, list] = defaultdict(list)
    for s in ctx.scenes:
        g[s.chapter_id].append(s)
    return g


# ───────────────────────── A01 · plot ─────────────────────────


@skill("SK01")
def sk01_premise(ctx: ToolContext, provider: Provider, opts: dict[str, Any]) -> SkillResult:
    r = SkillResult(uncertainty="high")
    p = ctx.project
    if not (p.logline or "").strip():
        r.find("لا توجد جملة محورية (logline) للمشروع؛ تحديدها يسهّل قياس انحراف الفصول عن الصراع المركزي.",
               certainty="supported", area="بنية")
    conflicts = [s for s in ctx.scenes if (s.node.meta or {}).get("conflict")]
    r.metrics = {"scenes_with_conflict": len(conflicts), "scenes": len(ctx.scenes)}
    if ctx.scenes and len(conflicts) / len(ctx.scenes) < 0.5:
        r.find(f"{len(ctx.scenes) - len(conflicts)} من {len(ctx.scenes)} وحدة سردية بلا صراع مُعلن في مصفوفة المشاهد.",
               certainty="supported", area="بنية")
    if provider.available() and opts.get("allow_model"):
        try:
            c = provider.complete(
                "أنت مستشار حبكة. اقترح ولا تفرض. أجب بـ JSON فقط: {\"alternatives\":[{\"premise\":\"\",\"conflict\":\"\",\"why\":\"\"}]}",
                f"عنوان: {p.title}\nنوع: {p.genre}\nوصف: {p.description}\nجملة محورية: {p.logline}\n"
                "اقترح ثلاث صيغ بديلة للأطروحة والصراع المركزي، لا تكتب نصاً روائياً.", 1200)
            r.tokens += c.input_tokens + c.output_tokens
            data = parse_json_block(c.text) or {}
            for alt in (data.get("alternatives") or [])[:3]:
                if isinstance(alt, dict) and alt.get("premise"):
                    if ctx.create_proposal(skill_id="SK01", kind="note", title="بديل للأطروحة: " + str(alt["premise"])[:120],
                                           rationale=str(alt.get("why", "")), payload={"alternative": alt},
                                           risk="LOW", certainty="speculative"):
                        r.proposals_created += 1
        except ProviderUnavailable as e:
            r.warnings.append(f"تعذر التوليد: {e}")
    elif not provider.available():
        r.warnings.append("توليد البدائل يتطلب مزوداً نموذجياً مفعلاً؛ أُجري الفحص البنيوي فقط.")
    r.summary = "فحص الأطروحة والصراع المركزي" + (" مع بدائل مقترحة" if r.proposals_created else "")
    return r


@skill("SK02")
def sk02_structure(ctx: ToolContext, provider: Provider, opts: dict[str, Any]) -> SkillResult:
    r = SkillResult(uncertainty="medium")
    groups = chapter_groups(ctx)
    sizes = {cid: sum(s.doc.word_count for s in lst) for cid, lst in groups.items() if cid}
    if not sizes:
        r.summary = "لا توجد فصول ذات نص بعد."
        return r
    med = statistics.median(sizes.values()) or 1
    total = sum(sizes.values())
    r.metrics = {"chapters": len(sizes), "median_words": med, "total_words": total,
                 "chapter_words": {ctx.labels.get(k, str(k)): v for k, v in sizes.items()}}
    for cid, n in sizes.items():
        lbl = ctx.labels.get(cid, "")
        if med >= 300 and n > 2.5 * med:
            r.find(f"{lbl} أطول من وسيط الفصول بـ {n / med:.1f} ضعف ({n} كلمة) — قد يستحق التقسيم.",
                   kind="taste", area="بنية", evidence=[{"kind": "node", "node_id": str(cid), "label": lbl}])
        elif med >= 300 and n < 0.3 * med:
            r.find(f"{lbl} قصير جداً قياساً بالوسيط ({n} كلمة مقابل {med:.0f}).", kind="taste", area="بنية",
                   evidence=[{"kind": "node", "node_id": str(cid), "label": lbl}])
    missing = [s for s in ctx.scenes if s.node.type == "scene" and not all(
        (s.node.meta or {}).get(k) for k in ("goal", "conflict", "outcome"))]
    if missing:
        r.find(f"{len(missing)} مشهداً تنقصه خانة الهدف أو الصراع أو النتيجة في مصفوفة المشاهد.",
               certainty="supported", area="بنية", evidence=[ev(s) for s in missing[:8]])
    r.summary = f"بنية من {len(sizes)} فصلاً و{total} كلمة؛ وسيط الفصل {med:.0f} كلمة."
    return r


@skill("SK10")
def sk10_scene(ctx: ToolContext, provider: Provider, opts: dict[str, Any]) -> SkillResult:
    r = SkillResult(uncertainty="medium")
    rows = []
    for s in ctx.scenes:
        if s.node.type != "scene":
            continue
        m = s.node.meta or {}
        filled = sum(bool(m.get(k)) for k in ("goal", "conflict", "outcome", "pov_character_id", "place_id",
                                              "story_time", "new_information"))
        rows.append({"label": s.label, "words": s.doc.word_count, "matrix_filled": filled, "of": 7,
                     "dialogue_ratio": round(dialogue_ratio(s.text), 2)})
        if s.doc.word_count and s.doc.word_count < 120:
            r.find(f"{s.label}: مشهد قصير جداً ({s.doc.word_count} كلمة) — هل هو مشهد أم انتقال؟",
                   kind="taste", area="بنية", evidence=[ev(s)])
        if not m.get("new_information") and s.doc.word_count > 0:
            r.find(f"{s.label}: لم تُسجَّل «المعلومة الجديدة» التي يضيفها المشهد.", certainty="supported",
                   area="بنية", evidence=[ev(s)])
    r.metrics = {"scene_matrix": rows}
    r.summary = f"مصفوفة {len(rows)} مشهداً."
    return r


@skill("SK11")
def sk11_rhythm(ctx: ToolContext, provider: Provider, opts: dict[str, Any]) -> SkillResult:
    r = SkillResult(uncertainty="medium")
    curve = []
    for s in ctx.scenes:
        sl = [count_words(x) for x in sentences(s.text)]
        sl = [x for x in sl if x]
        if not sl:
            continue
        mean = statistics.mean(sl)
        cv = statistics.pstdev(sl) / mean if mean else 0
        curve.append({"label": s.label, "mean_sentence": round(mean, 1), "cv": round(cv, 2),
                      "dialogue": round(dialogue_ratio(s.text), 2)})
        if len(sl) >= 15 and cv < 0.25:
            r.find(f"{s.label}: أطوال الجمل متقاربة جداً (معامل تباين {cv:.2f}) — قد يبدو الإيقاع رتيباً.",
                   kind="taste", area="إيقاع", evidence=[ev(s)])
        for m in re.finditer(r"[^\.\!\?؟…\n]+", s.text):
            if count_words(m.group(0)) > 70:
                r.find(f"{s.label}: جملة من {count_words(m.group(0))} كلمة دون توقف.", certainty="supported",
                       area="لغة", evidence=[ev(s, m.start(), m.end())])
                break
    r.metrics = {"rhythm_curve": curve}
    r.summary = "منحنى الإيقاع (طول الجمل وتباينها ونسبة الحوار) لكل وحدة."
    return r


# ───────────────────────── A02 / A06 · characters & affect ─────────────────────────


def mention_map(ctx: ToolContext) -> dict[Any, list[tuple[Any, int]]]:
    """character id → [(scene, mentions)] in reading order, one regex pass per scene."""
    matcher = continuity.NameMatcher(ctx.characters)
    out: dict[Any, list[tuple[Any, int]]] = {c.id: [] for c in ctx.characters}
    for s in ctx.scenes:
        counts: Counter = Counter(c.id for _, _, c in matcher.find(normalize_ar(s.text)))
        for cid, k in counts.items():
            out[cid].append((s, k))
    return out


@skill("SK03")
def sk03_characters(ctx: ToolContext, provider: Provider, opts: dict[str, Any]) -> SkillResult:
    r = SkillResult(uncertainty="medium")
    mm = mention_map(ctx)
    table = []
    for c in ctx.characters:
        lst = mm.get(c.id, [])
        prof = c.profile or {}
        table.append({"character": c.canonical_name, "mentions": sum(k for _, k in lst),
                      "first": lst[0][0].label if lst else None, "last": lst[-1][0].label if lst else None,
                      "scenes": len(lst)})
        if not lst and ctx.scenes:
            r.find(f"«{c.canonical_name}» مسجّلة في الأطلس ولا تظهر في النص.", certainty="supported", area="شخصيات")
        missing = [f for f, ar in (("goal", "الهدف"), ("obstacle", "العائق"), ("secret", "السر"), ("arc", "قوس التحول"))
                   if not prof.get(f)]
        if missing and lst and sum(k for _, k in lst) >= 5:
            r.find(f"«{c.canonical_name}» شخصية حاضرة ({sum(k for _, k in lst)} ذكراً) وتنقص ملفها: "
                   + "، ".join(dict((("goal", "الهدف"), ("obstacle", "العائق"), ("secret", "السر"),
                                     ("arc", "قوس التحول")))[m] for m in missing) + ".",
                   certainty="supported", area="شخصيات")
        if len(lst) >= 2 and len(ctx.scenes) >= 6:
            idx = [ctx.scenes.index(s) for s, _ in lst]
            gaps = [b - a for a, b in zip(idx, idx[1:], strict=False)]
            if gaps and max(gaps) > max(5, len(ctx.scenes) // 3):
                r.find(f"«{c.canonical_name}» تغيب {max(gaps)} وحدات سردية متتالية — تحقق أن الغياب مقصود.",
                       kind="taste", area="شخصيات")
    pov = Counter((s.node.meta or {}).get("pov_character_id") for s in ctx.scenes if s.node.type == "scene")
    names = {str(c.id): c.canonical_name for c in ctx.characters}
    r.metrics = {"appearances": table, "pov_distribution": {names.get(str(k), "غير محدد"): v for k, v in pov.items()}}
    r.summary = f"خريطة حضور {len(ctx.characters)} شخصية."
    return r


AFFECT = {
    "fear": "خوف خاف خائف رعب ذعر فزع رهبه قلق ارتجف ارتعش هلع",
    "sadness": "حزن حزين بكي بكاء دموع دمع اسي حسره فقد وحده كابه ياس",
    "anger": "غضب غاضب ثار ثوره صرخ حنق سخط كراهيه حقد",
    "joy": "فرح سعاده ضحك ابتسم ابتسامه بهجه سرور امل نشوه",
    "tension": "فجاه صمت انتظر خطر سر مطارده هرب ركض دم موت",
}
AFFECT_STEMS = {k: {t for w in v.split() for t in search_tokens(w)} for k, v in AFFECT.items()}


@skill("SK17")
def sk17_affect(ctx: ToolContext, provider: Provider, opts: dict[str, Any]) -> SkillResult:
    r = SkillResult(uncertainty="high")
    curve = []
    for s in ctx.scenes:
        toks = search_tokens(s.text)
        n = len(toks) or 1
        row = {"label": s.label}
        for k, stems in AFFECT_STEMS.items():
            row[k] = round(1000 * sum(1 for t in toks if t in stems) / n, 1)
        curve.append(row)
    r.metrics = {"affect_curve": curve, "lexicon_size": sum(len(v) for v in AFFECT_STEMS.values())}
    if len(curve) >= 4:
        flat = all(abs(c["tension"] - curve[0]["tension"]) < 1 for c in curve)
        if flat:
            r.find("منحنى ألفاظ التوتر مسطّح عبر الوحدات — مؤشر معجمي فقط لا يقيس الأثر الفعلي.",
                   certainty="speculative", kind="taste", area="تأثير")
    r.warnings.append("المنحنى معجمي تقريبي (فرضية)، لا يمثل استجابة قراء حقيقيين.")
    r.summary = "منحنى وجداني معجمي لكل وحدة (افتراضي)."
    return r


@skill("SK12")
def sk12_depth(ctx: ToolContext, provider: Provider, opts: dict[str, Any]) -> SkillResult:
    r = SkillResult(uncertainty="high")
    for c in ctx.characters:
        prof = c.profile or {}
        if not prof.get("secret") or not prof.get("arc"):
            r.find(f"سؤال للكاتب: ما الذي تخفيه «{c.canonical_name}» عن نفسها، وكيف يتغير فهمها لذاتها بين البداية والنهاية؟",
                   certainty="speculative", kind="taste", area="عمق")
    if not provider.available() or not opts.get("allow_model"):
        r.warnings.append("التحليل النفسي والفلسفي المعمّق يتطلب مزوداً نموذجياً مفعلاً وموافقة نقل البيانات؛ "
                          "عُرضت أسئلة توجيهية فقط ولم يُصطنع تحليل.")
        r.summary = "أسئلة توجيهية للعمق (بلا نموذج)."
        return r
    sample = "\n\n".join(s.text[:1500] for s in ctx.scenes[:3])
    try:
        c = provider.complete(
            "أنت مستشار عمق نفسي وفكري لرواية. لا تشخّص أشخاصاً حقيقيين ولا تفرض فلسفة. أجب JSON فقط: "
            "{\"findings\":[{\"claim\":\"\",\"quote\":\"\"}]}. كل claim يجب أن يستند إلى quote حرفي من النص.",
            sample, 1500)
        r.tokens += c.input_tokens + c.output_tokens
        for f in (parse_json_block(c.text) or {}).get("findings", [])[:8]:
            q = str(f.get("quote", ""))
            if q and any(q in s.text for s in ctx.scenes):
                r.find(str(f.get("claim", "")), certainty="inferred", kind="taste", area="عمق",
                       evidence=[{"kind": "quote", "quote": q}])
            else:
                r.warnings.append("أُسقطت ملاحظة نموذجية لا تستند إلى اقتباس حرفي من النص.")
    except ProviderUnavailable as e:
        r.warnings.append(str(e))
    r.summary = "ملاحظات العمق مدعومة باقتباسات."
    return r


# ───────────────────────── A03 · world & time ─────────────────────────


@skill("SK04")
def sk04_world(ctx: ToolContext, provider: Provider, opts: dict[str, Any]) -> SkillResult:
    r = SkillResult(uncertainty="medium")
    text_all = normalize_ar(" ".join(s.text for s in ctx.scenes))
    used_ids = {str((s.node.meta or {}).get("place_id")) for s in ctx.scenes}
    for p in ctx.places:
        names = [normalize_ar(x) for x in [p.name, *(p.aliases or [])] if x.strip()]
        in_text = any(n in text_all for n in names)
        if not in_text and str(p.id) not in used_ids:
            r.find(f"المكان «{p.name}» غير مذكور في النص ولا مرتبط بأي مشهد.", certainty="supported", area="عالم")
        if not (p.profile or {}).get("description"):
            r.find(f"المكان «{p.name}» بلا وصف في ملف العالم.", certainty="supported", area="عالم")
    r.summary = f"فحص {len(ctx.places)} مكاناً."
    return r


@skill("SK05")
def sk05_timeline(ctx: ToolContext, provider: Provider, opts: dict[str, Any]) -> SkillResult:
    r = SkillResult(uncertainty="medium")
    timed = [e for e in ctx.events if e.story_time_start is not None]
    untimed = [e for e in ctx.events if e.story_time_start is None]
    if untimed:
        r.find(f"{len(untimed)} حدثاً بلا زمن قصة (مقبول إن كان مجهولاً عمداً؛ وسمه uncertainty=unknown).",
               certainty="supported", area="زمن")
    narrated = sorted([e for e in timed if e.narration_order is not None], key=lambda e: e.narration_order or 0)
    flashbacks = []
    for a, b in zip(narrated, narrated[1:], strict=False):
        if (b.story_time_start or 0) < (a.story_time_start or 0):
            flashbacks.append({"from": a.title, "to": b.title, "jump_back": (a.story_time_start or 0) - (b.story_time_start or 0)})
    if flashbacks:
        r.find(f"{len(flashbacks)} قفزة إلى الوراء في ترتيب السرد (استرجاع) — تحقق من وضوح الإشارات الزمنية للقارئ.",
               certainty="supported", kind="taste", area="زمن")
    untimed_scenes = [s for s in ctx.scenes if s.node.type == "scene" and (s.node.meta or {}).get("story_time") is None]
    r.metrics = {"events": len(ctx.events), "timed": len(timed), "flashbacks": flashbacks,
                 "scenes_without_story_time": len(untimed_scenes)}
    r.summary = f"خط زمني: {len(timed)} حدثاً مؤرخاً، {len(flashbacks)} استرجاعاً."
    return r


@skill("SK09")
def sk09_motifs(ctx: ToolContext, provider: Provider, opts: dict[str, Any]) -> SkillResult:
    r = SkillResult(uncertainty="high")
    names = set()
    for c in ctx.characters:
        for n in [c.canonical_name, *(c.aliases or [])]:
            names.update(search_tokens(n))
    spread: dict[str, set] = defaultdict(set)
    freq: Counter = Counter()
    for s in ctx.scenes:
        toks = [t for t in search_tokens(s.text) if len(t) >= 3 and t not in names and not t.isdigit()]
        freq.update(toks)
        for t in set(toks):
            spread[t].add(s.chapter_id)
    chapters = len({s.chapter_id for s in ctx.scenes}) or 1
    cands = [(t, len(spread[t]), freq[t]) for t in spread if len(spread[t]) >= max(3, chapters // 2) and freq[t] >= 4]
    cands.sort(key=lambda x: (x[1], x[2]), reverse=True)
    r.metrics = {"candidates": [{"stem": t, "chapters": c, "count": f} for t, c, f in cands[:15]]}
    if cands:
        r.find("مفردات متكررة عبر الفصول قد تكون موتيفات (فرضية تحتاج قرار الكاتب): "
               + "، ".join(t for t, _, _ in cands[:8]), certainty="speculative", kind="taste", area="رموز")
    r.summary = "مرشحات الموتيفات (جذوع متكررة عبر الفصول)."
    return r


# ───────────────────────── A04 · voice ─────────────────────────

FIRST_PERSON = re.compile(r"(?<![^\W_])(?:انا|أنا|كنت|قلت|رأيت|ذهبت|نفسي|عيني|قلبي)(?![^\W_])")


@skill("SK06")
def sk06_pov(ctx: ToolContext, provider: Provider, opts: dict[str, Any]) -> SkillResult:
    r = SkillResult(uncertainty="medium")
    rows = []
    for s in ctx.scenes:
        n = s.doc.word_count or 1
        fp = len(FIRST_PERSON.findall(normalize_ar(s.text)))
        rows.append({"label": s.label, "first_person_per_1k": round(1000 * fp / n, 1),
                     "pov_set": bool((s.node.meta or {}).get("pov_character_id"))})
    if rows:
        vals = [x["first_person_per_1k"] for x in rows]
        med = statistics.median(vals)
        for x, s in zip(rows, ctx.scenes, strict=True):
            if med < 2 and x["first_person_per_1k"] > 12:
                r.find(f"{x['label']}: كثافة ضمير المتكلم أعلى بكثير من بقية النص — تحقق من ثبات التبئير أو أنه مقصود (رسالة/مذكرات).",
                       kind="objective", certainty="inferred", area="راوٍ", evidence=[ev(s)])
    unset = [x for x in rows if not x["pov_set"]]
    if unset:
        r.find(f"{len(unset)} وحدة دون تحديد شخصية التبئير في المصفوفة.", certainty="supported", area="راوٍ")
    r.metrics = {"pov": rows}
    r.summary = "فحص التبئير وثبات ضمير السرد."
    return r


SPEECH_TAGS = re.compile(r"(?<![^\W_])(?:قال|قالت|رد|ردت|اجاب|اجابت|سال|سالت)(?![^\W_])")


@skill("SK07")
def sk07_dialogue(ctx: ToolContext, provider: Provider, opts: dict[str, Any]) -> SkillResult:
    r = SkillResult(uncertainty="medium")
    rows = []
    for s in ctx.scenes:
        dr = dialogue_ratio(s.text)
        tags = len(SPEECH_TAGS.findall(normalize_ar(s.text)))
        rows.append({"label": s.label, "dialogue_ratio": round(dr, 2), "speech_tags": tags})
        if tags >= 12 and s.doc.word_count and tags / s.doc.word_count > 0.02:
            r.find(f"{s.label}: {tags} فعل إسناد للكلام (قال/ردّ…) — قد يفيد تنويعها أو حذف بعضها حين يتضح المتكلم.",
                   kind="taste", area="حوار", evidence=[ev(s)])
    r.metrics = {"dialogue": rows}
    r.summary = "نسبة الحوار وأفعال الإسناد لكل وحدة."
    r.warnings.append("لا يغيّر المستشار العامية إلى الفصحى ولا العكس.")
    return r


@skill("SK08")
def sk08_style(ctx: ToolContext, provider: Provider, opts: dict[str, Any]) -> SkillResult:
    r = SkillResult(uncertainty="medium")
    prof = ctx.style_profile()
    if not prof:
        r.warnings.append("لا توجد بصمة أسلوبية معتمدة بعينات مملوكة؛ أنشئها من «البصمة الأسلوبية» أولاً.")
        r.summary = "لا مقارنة دون بصمة."
        return r
    for s in ctx.scenes:
        if s.doc.word_count < 300:
            continue
        devs = compare_features(prof.features, extract_features(s.text))
        if devs:
            r.find(f"{s.label}: ينحرف عن البصمة في " + "، ".join(d["label"] for d in devs[:3]) + ".",
                   kind="objective", certainty="inferred", area="أسلوب", evidence=[ev(s, note="; ".join(
                       f"{d['label']}: {d['value']} مقابل {d['baseline']}" for d in devs[:3]))])
    r.summary = f"مقارنة الوحدات ببصمة «{prof.name}»."
    return r


# ───────────────────────── A05 · research ─────────────────────────

HISTORICAL = re.compile(r"(?:(?:عام|سنه|سنة|في)\s+)?(?:1[0-9]{3}|20[0-2][0-9])(?:\s*(?:م|ه|هـ))?|القرن\s+\S+")


@skill("SK13")
def sk13_research(ctx: ToolContext, provider: Provider, opts: dict[str, Any]) -> SkillResult:
    r = SkillResult(uncertainty="medium")
    checked = verified = 0
    for s in ctx.scenes:
        for sent in sentences(s.text):
            if not HISTORICAL.search(sent) or count_words(sent) < 4:
                continue
            checked += 1
            if checked > 40:
                break
            res = ctx.retrieve_sources(sent, k=2)
            start = s.text.find(sent)
            for h in res["hits"]:
                if h["suspicious_instructions"]:
                    msg = (f"المقطع {h['locator']} من «{h['source_title']}» يحوي عبارات تشبه أوامر؛ "
                           "عومل بيانات فقط ولم يُنفَّذ شيء منه.")
                    if msg not in r.warnings:
                        r.warnings.append(msg)
            if res["verdict"] == "evidence_found":
                verified += 1
                hit = res["hits"][0]
                r.citations.append({"claim": sent[:300], "chunk_id": hit["chunk_id"], "locator": hit["locator"],
                                    "source": hit["source_title"], "score": hit["score"]})
                r.find(f"{s.label}: ادعاء تاريخي له مقطع مرتبط في «{hit['source_title']}» ({hit['locator']}) — راجعه.",
                       certainty="inferred", area="مصداقية",
                       evidence=[ev(s, start, start + len(sent)), {"kind": "source", "chunk_id": hit["chunk_id"],
                                                                   "locator": hit["locator"]}])
            else:
                r.find(f"{s.label}: «{sent[:90]}…» — غير متحقق: لا توجد أدلة كافية في مصادر المشروع.",
                       certainty="speculative", area="مصداقية", evidence=[ev(s, start, start + len(sent))])
    r.metrics = {"historical_claims_checked": checked, "with_evidence": verified}
    r.summary = f"فُحص {checked} ادعاءً تاريخياً؛ {verified} لها مقاطع مرتبطة، والباقي «غير متحقق»."
    return r


# ───────────────────────── A07 · continuity ─────────────────────────


@skill("SK16")
def sk16_continuity(ctx: ToolContext, provider: Provider, opts: dict[str, Any]) -> SkillResult:
    r = SkillResult(uncertainty="low")
    stats = continuity.run_scan(ctx.db_for_continuity, ctx.project_id)
    r.metrics = stats
    r.summary = (f"فحص الاستمرارية: {stats['found']} تعارضاً قائماً ({stats['created']} جديد، "
                 f"{stats['auto_resolved']} زال بعد آخر تعديل).")
    if stats["found"]:
        r.find(r.summary + " افتح لوحة الاستمرارية لرؤية الشواهد.", certainty="supported", area="استمرارية")
    return r


# ───────────────────────── A08 · memory ─────────────────────────


@skill("SK21")
def sk21_memory(ctx: ToolContext, provider: Provider, opts: dict[str, Any]) -> SkillResult:
    """Propose draft facts from the text (ages at story time). Becoming canon needs the author."""
    r = SkillResult(uncertainty="medium")
    scan = continuity.Scan(ctx.db_for_continuity, ctx.project_id)
    _, ages = scan.mentions()
    existing = {(f.subject_id, f.predicate, (f.object or {}).get("value")) for f in ctx.search_canon()}
    for a in ages[:60]:
        t = continuity._story_time(a.node, scan.by_id)
        if t is None:
            continue
        birth = round(t - a.age)
        key = (a.character.id, "birth_year", birth)
        if key in existing:
            continue
        evd = continuity.text_evidence(a.doc, a.node, scan.labels.get(a.node.id, ""), a.start, a.end)
        if ctx.create_proposal(
            skill_id="SK21", kind="fact", risk="MEDIUM", certainty="inferred",
            title=f"حقيقة مقترحة: «{a.character.canonical_name}» وُلد نحو {birth}",
            rationale=f"النص يذكر عمر {a.age} في زمن قصة {t:g}. القبول يضيفها مسودةً، والكانون بقرارك.",
            payload={"subject_type": "character", "subject_id": str(a.character.id),
                     "subject_label": a.character.canonical_name, "predicate": "birth_year",
                     "object": {"value": birth}, "statement": f"سنة ميلاد {a.character.canonical_name} نحو {birth}"},
            evidence=[evd],
        ):
            r.proposals_created += 1
    r.summary = f"اقترح أمين الذاكرة {r.proposals_created} حقيقة مسودة من النص."
    return r


# ───────────────────────── A09 · counter-critique ─────────────────────────


@skill("SK14")
def sk14_critique(ctx: ToolContext, provider: Provider, opts: dict[str, Any]) -> SkillResult:
    r = SkillResult(uncertainty="high")
    groups = chapter_groups(ctx)
    openings = Counter()
    for cid, lst in groups.items():
        if not cid or not lst:
            continue
        first = words(lst[0].text)[:1]
        if first:
            openings[normalize_ar(first[0])] += 1
    for w, k in openings.items():
        if k >= 3 and k >= len(groups) * 0.4:
            r.find(f"{k} فصول تبدأ بالكلمة نفسها «{w}» — اعتراض ذوقي: قد يتوقع القارئ النمط.",
                   kind="taste", area="بنية")
    hooks = sum(1 for lst in groups.values() if lst and lst[-1].text.strip()[-1:] in "؟?…!")
    if len(groups) >= 4:
        r.find(f"{hooks} من {len(groups)} فصلاً تنتهي بعلامة تعليق (؟ … !). ليس معياراً للجودة؛ بعض النهايات الهادئة أقوى.",
               certainty="supported", kind="objective", area="إيقاع")
    total = sum(s.doc.word_count for s in ctx.scenes) or 1
    cum, mid_label = 0, None
    for s in ctx.scenes:
        cum += s.doc.word_count
        if cum >= total / 2:
            mid_label = s.label
            break
    if mid_label:
        r.find(f"منتصف الرواية بالكلمات يقع في {mid_label}. اعتراض بديل: هل يقع عنده تحوّل يعيد تعريف الصراع؟",
               kind="taste", area="بنية")
    r.summary = "اعتراضات مضادة مصنّفة: موضوعي مقابل ذوقي."
    r.warnings.append("النقد المضاد يقترح زوايا بديلة ولا يصدر أحكاماً مطلقة.")
    return r


# ───────────────────────── A10 / A11 · editing ─────────────────────────

AR = r"؀-ۿ"
LINT_RULES: list[tuple[str, re.Pattern[str], Callable[[re.Match[str]], str], str]] = [
    ("latin_comma", re.compile(rf"(?<=[{AR}])\s*,\s*(?=[{AR}])"), lambda m: "، ", "الفاصلة العربية «،» في سياق عربي"),
    ("latin_question", re.compile(rf"(?<=[{AR}])\s*\?"), lambda m: "؟", "علامة الاستفهام العربية «؟»"),
    ("latin_semicolon", re.compile(rf"(?<=[{AR}])\s*;\s*"), lambda m: "؛ ", "الفاصلة المنقوطة العربية «؛»"),
    ("space_before_punct", re.compile(r"(?<=\S)[ \t]+(?=[،؛؟!\.:…»])"), lambda m: "", "حذف المسافة قبل علامة الترقيم"),
    ("space_after_comma", re.compile(rf"([،؛])(?=[{AR}])"), lambda m: m.group(1) + " ", "مسافة بعد الفاصلة"),
    ("double_space", re.compile(r"(?<=\S) {2,}(?=\S)"), lambda m: " ", "مسافة مزدوجة"),
    ("ellipsis", re.compile(r"(?<!\.)\.{3,}(?!\.)|(?<![\.…])\.\.(?![\.…])"), lambda m: "…", "علامة الحذف «…»"),
    ("tatweel", re.compile(r"(?<=[ؠ-ي])ـ+(?=[ؠ-ي])"), lambda m: "", "حذف التطويل «ـ» من المتن"),
]
REPEATED_WORD = re.compile(r"(?<![^\W_])([^\W\d_]{2,})(\s+)\1(?![^\W_])")
INTENTIONAL_REPEATS = {"رويدا", "رويداً", "شيئا", "شيئاً", "قليلا", "قليلاً", "رويدًا", "شيئًا", "قليلًا", "بعيدا",
                       "بعيداً", "دق", "طق", "هيا", "لا", "لن", "كلا", "نعم"}


@skill("SK15")
def sk15_editing(ctx: ToolContext, provider: Provider, opts: dict[str, Any]) -> SkillResult:
    r = SkillResult(uncertainty="low")
    agent = ctx.agent_id
    by_rule: Counter = Counter()
    for s in ctx.scenes:
        blocks_ = s.blocks
        # A10 also spots duplicated consecutive paragraphs (proposes deletion, never deletes)
        if agent in ("A10", "A00"):
            for i in range(1, len(blocks_)):
                a, b = blocks_[i - 1], blocks_[i]
                if b["text"].strip() and normalize_ar(a["text"].strip()) == normalize_ar(b["text"].strip()) \
                        and count_words(b["text"]) >= 6:
                    if ctx.create_proposal(
                        skill_id="SK15", document=s.doc, risk="MEDIUM", certainty="supported",
                        title=f"{s.label}: حذف فقرة مكررة حرفياً",
                        rationale="الفقرة تطابق الفقرة السابقة لها حرفياً — غالباً تكرار لصق. لن تُحذف إلا بموافقتك.",
                        ops=[{"op": "delete_block", "block": b["index"], "expected": b["text"]}],
                        evidence=[ev(s, note=f"الفقرتان {a['index'] + 1} و{b['index'] + 1}")],
                    ):
                        r.proposals_created += 1
                        by_rule["duplicate_paragraph"] += 1
        if agent not in ("A11", "A10", "A00"):
            continue
        for rule, rx, repl, label in LINT_RULES:
            ops = []
            for b in blocks_:
                if not b["editable"] or not is_arabic(b["text"]):
                    continue
                for m in rx.finditer(b["text"]):
                    new = repl(m)
                    if new != m.group(0):
                        ops.append({"op": "replace_text", "block": b["index"], "start": m.start(), "end": m.end(),
                                    "expected": m.group(0), "text": new})
            if ops:
                if ctx.create_proposal(
                    skill_id="SK15", document=s.doc, risk="LOW", certainty="supported",
                    title=f"{s.label}: {label} ({len(ops)} موضعاً)",
                    rationale=f"تدقيق لغوي آلي حتمي: {label}. لا يمس الأسلوب ولا مستوى اللغة.",
                    ops=ops[:200], evidence=[ev(s)],
                ):
                    r.proposals_created += 1
                    by_rule[rule] += len(ops)
        # repeated words: proposed individually (could be intentional)
        for b in blocks_:
            if not b["editable"]:
                continue
            for m in REPEATED_WORD.finditer(b["text"]):
                w = m.group(1)
                if w in INTENTIONAL_REPEATS or strip_diacritics(w) in INTENTIONAL_REPEATS:
                    continue
                if ctx.create_proposal(
                    skill_id="SK15", document=s.doc, risk="LOW", certainty="inferred",
                    title=f"{s.label}: كلمة مكررة «{w} {w}»",
                    rationale="تكرار متتالٍ قد يكون سهواً. إن كان توكيداً مقصوداً فارفض المقترح.",
                    ops=[{"op": "replace_text", "block": b["index"], "start": m.start(), "end": m.end(),
                          "expected": m.group(0), "text": w}],
                    evidence=[ev(s)],
                ):
                    r.proposals_created += 1
                    by_rule["repeated_word"] += 1
    if provider.available() and opts.get("allow_model") and agent == "A10":
        r.tokens += _model_line_edits(ctx, provider, r)
    elif agent == "A10" and not provider.available():
        r.warnings.append("التحرير الأسلوبي التوليدي يتطلب مزوداً مفعلاً؛ قُدمت التصويبات الحتمية فقط.")
    r.metrics = {"by_rule": dict(by_rule)}
    r.summary = f"أنشأ {r.proposals_created} مقترح تحرير قابلاً للمراجعة (لا تعديل مباشر)."
    return r


def _model_line_edits(ctx: ToolContext, provider: Provider, r: SkillResult) -> int:
    used = 0
    for s in ctx.scenes[:4]:
        editable = [b for b in s.blocks if b["editable"] and b["text"].strip()][:12]
        if not editable:
            continue
        payload = "\n".join(f"[{b['index']}] {b['text']}" for b in editable)
        try:
            c = provider.complete(
                "أنت محرر أدبي عربي. لا تعيد الكتابة، اقترح تعديلات صغيرة دقيقة فقط، ولا تحوّل العامية إلى فصحى. "
                "أجب JSON فقط: {\"edits\":[{\"block\":0,\"expected\":\"مقطع حرفي من الفقرة\",\"text\":\"البديل\","
                "\"why\":\"أثر التعديل في الإيقاع أو الصوت\"}]}",
                payload, 1500)
        except ProviderUnavailable as e:
            r.warnings.append(str(e))
            return used
        used += c.input_tokens + c.output_tokens
        for e in (parse_json_block(c.text) or {}).get("edits", [])[:10]:
            try:
                bi, exp, new = int(e["block"]), str(e["expected"]), str(e["text"])
            except (KeyError, ValueError, TypeError):
                continue
            blk = next((b for b in editable if b["index"] == bi), None)
            pos = blk["text"].find(exp) if blk and exp else -1
            if pos < 0 or exp == new:
                r.warnings.append("أُسقط تعديل نموذجي لا يطابق النص الحالي حرفياً.")
                continue
            if ctx.create_proposal(
                skill_id="SK15", document=s.doc, risk="MEDIUM", certainty="speculative",
                title=f"{s.label}: اقتراح تحريري", rationale=str(e.get("why", ""))[:600],
                ops=[{"op": "replace_text", "block": bi, "start": pos, "end": pos + len(exp), "expected": exp, "text": new}],
                evidence=[ev(s)],
            ):
                r.proposals_created += 1
    return used


# ───────────────────────── A12 · originality & publishing ─────────────────────────


def _shingles(text: str, n: int = 8) -> dict[tuple[str, ...], int]:
    toks = [normalize_ar(w) for w in words(text)]
    return {tuple(toks[i:i + n]): i for i in range(max(0, len(toks) - n + 1))}


@skill("SK18")
def sk18_reading(ctx: ToolContext, provider: Provider, opts: dict[str, Any]) -> SkillResult:
    r = SkillResult(uncertainty="high")
    rows = []
    for s in ctx.scenes:
        rows.append({"label": s.label, "minutes": round(s.doc.word_count / 180, 1),
                     "ends_with_hook": s.text.strip()[-1:] in "؟?…!" if s.text.strip() else False})
    r.metrics = {"reading": rows, "total_minutes": round(sum(x["minutes"] for x in rows), 1)}
    r.warnings.append("محاكاة افتراضية (180 كلمة/دقيقة تقديراً) — ليست رأي قارئ حقيقي.")
    r.summary = f"زمن قراءة تقديري ≈ {r.metrics['total_minutes']} دقيقة."
    return r


@skill("SK19")
def sk19_originality(ctx: ToolContext, provider: Provider, opts: dict[str, Any]) -> SkillResult:
    from sqlalchemy import select

    from ..models import SourceChunk, SourceFile

    r = SkillResult(uncertainty="medium")
    db = ctx.db_for_continuity
    srcs = list(db.scalars(select(SourceFile).where(SourceFile.project_id == ctx.project_id)))
    unknown = [s.filename for s in srcs if s.license_state == "unknown"]
    if unknown:
        r.find(f"{len(unknown)} مصدراً بحالة ترخيص «غير معروفة» ولا يُستخدم في الاسترجاع: " + "، ".join(unknown[:5]),
               certainty="supported", area="حقوق")
    src_sh: dict[tuple[str, ...], str] = {}
    for ch in db.scalars(select(SourceChunk).where(SourceChunk.project_id == ctx.project_id)):
        for sh in _shingles(ch.content):
            src_sh.setdefault(sh, ch.locator)
    overlaps = 0
    seen_internal: dict[tuple[str, ...], str] = {}
    for s in ctx.scenes:
        for sh in _shingles(s.text):
            if sh in src_sh:
                overlaps += 1
                if overlaps <= 5:
                    r.find(f"{s.label}: تطابق حرفي (8 كلمات فأكثر) مع مصدر مرفوع ({src_sh[sh]}) — وثّق الاقتباس أو أعد الصياغة.",
                           certainty="supported", area="أصالة", evidence=[ev(s, note=" ".join(sh))])
            other = seen_internal.get(sh)
            if other and other != s.label:
                r.find(f"تكرار ذاتي حرفي بين {other} و{s.label}: «{' '.join(sh)}…»", certainty="supported",
                       kind="taste", area="أصالة")
                seen_internal[sh] = s.label
            seen_internal.setdefault(sh, s.label)
    r.findings = r.findings[:40]
    r.metrics = {"source_overlaps": overlaps}
    r.warnings.append("لا يضمن النظام انعدام التشابه مع نصوص خارج المشروع.")
    r.summary = f"تطابقات حرفية مع المصادر: {overlaps}."
    return r


@skill("SK20")
def sk20_publishing(ctx: ToolContext, provider: Provider, opts: dict[str, Any]) -> SkillResult:
    from sqlalchemy import func, select

    from ..models import Conflict, Manuscript, Proposal

    r = SkillResult(uncertainty="low")
    db = ctx.db_for_continuity
    checks = []
    ms = db.scalar(select(Manuscript).where(Manuscript.project_id == ctx.project_id))
    checks.append(("اسم المؤلف في البيانات الوصفية", bool(ms and ms.author_name)))
    chapters = [n for n in ctx.nodes if n.type == "chapter"]
    checks.append(("لكل فصل عنوان", all(n.title for n in chapters) if chapters else False))
    empty = [s.label for s in ctx.scenes if s.doc.word_count == 0 and s.node.type == "scene"]
    checks.append(("لا مشاهد فارغة", not empty))
    open_high = db.scalar(select(func.count()).select_from(Conflict).where(
        Conflict.project_id == ctx.project_id, Conflict.state == "open", Conflict.severity == "high")) or 0
    checks.append(("لا تعارضات استمرارية عالية مفتوحة", open_high == 0))
    pending = db.scalar(select(func.count()).select_from(Proposal).where(
        Proposal.project_id == ctx.project_id, Proposal.state == "pending")) or 0
    checks.append(("لا مقترحات معلقة", pending == 0))
    for label, ok in checks:
        if not ok:
            r.find(f"قائمة الإخراج: «{label}» غير مستوفى.", certainty="supported", area="نشر")
    r.metrics = {"checklist": [{"item": a, "ok": b} for a, b in checks], "empty_scenes": empty[:20]}
    r.summary = f"جاهزية الإخراج: {sum(1 for _, ok in checks if ok)}/{len(checks)}."
    return r
