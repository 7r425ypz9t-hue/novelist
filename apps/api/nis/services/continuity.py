"""Rule-based continuity engine (FR14, SK16, §9).

Pipeline: entity mention extraction → name normalization → approved facts/bible → temporal & relational rules
→ conflict report with evidence spans → human review. Every conflict carries ≥2 evidence items. Intentional
narrator contradictions are handled by *waivers* (state=waived + reason), which persist across re-scans (AT09).
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import CanonFact, Character, Conflict, Document, Event, Manuscript, Node, Place, utcnow
from ..security import sha256_hex
from ..text import TASHKEEL, _EASTERN_DIGITS, _NORM_MAP, block_offsets, locate
from .manuscript import labels, ordered_nodes

MEMORY_MARKERS = ("تذكر", "ذكري", "ذكرى", "المرحوم", "الراحل", "رحمه", "قبر", "حلم", "طيف", "صوره", "روح")

_UNITS = {
    "واحد": 1, "احد": 1, "اثنين": 2, "اثنتين": 2, "اثنان": 2, "ثلاث": 3, "ثلاثه": 3, "اربع": 4, "اربعه": 4,
    "خمس": 5, "خمسه": 5, "ست": 6, "سته": 6, "سبع": 7, "سبعه": 7, "ثماني": 8, "ثمان": 8, "ثمانيه": 8,
    "تسع": 9, "تسعه": 9, "عشر": 10, "عشره": 10,
    # ordinals, the usual way Arabic prose states an age: «في الثانية عشرة»، «في الخامسة والعشرين»
    "حادي": 1, "حاديه": 1, "ثاني": 2, "ثانيه": 2, "ثالث": 3, "ثالثه": 3, "رابع": 4, "رابعه": 4, "خامس": 5,
    "خامسه": 5, "سادس": 6, "سادسه": 6, "سابع": 7, "سابعه": 7, "ثامن": 8, "ثامنه": 8, "تاسع": 9, "تاسعه": 9,
    "عاشر": 10, "عاشره": 10,
}
_TENS = {"عشرين": 20, "ثلاثين": 30, "اربعين": 40, "خمسين": 50, "ستين": 60, "سبعين": 70, "ثمانين": 80,
         "تسعين": 90, "عشرون": 20, "ثلاثون": 30, "اربعون": 40, "خمسون": 50, "ستون": 60, "سبعون": 70,
         "ثمانون": 80, "تسعون": 90}
_NUM_WORD = "|".join(sorted(list(_UNITS) + list(_TENS), key=len, reverse=True))
_NUM_PHRASE = (r"(?:(?:" + _NUM_WORD + r")(?:\s+عشره?)?(?:\s+و\s*(?:ال)?(?:" + _NUM_WORD + r"))?)")
_AGE_RE = re.compile(
    r"(?:عمره|عمرها|عمري|سنه|سنها|يبلغ|تبلغ|بلغ|بلغت|ابن|ابنه|بنت|في|ذو|ذات)\s+(?:ال)?"
    r"(?P<num>\d{1,3}|" + _NUM_PHRASE + r")"
    r"\s*(?:عاما|عام|سنه|سنوات|سنين|ربيعا|خريفا|من\s+(?:العمر|عمره|عمرها|عمري))"
)


def norm_with_map(text: str) -> tuple[str, list[int]]:
    """Normalize Arabic text while keeping a char-index map back to the original string."""
    out, idx = [], []
    for i, ch in enumerate(text):
        if TASHKEEL.match(ch) or ch == "ـ":
            continue
        out.append(ch.translate(_NORM_MAP).translate(_EASTERN_DIGITS).lower())
        idx.append(i)
    idx.append(len(text))
    return "".join(out), idx


def parse_age(phrase: str) -> int | None:
    phrase = phrase.strip()
    if phrase.isdigit():
        return int(phrase)
    total = 0
    for part in re.split(r"\s+و\s*", phrase):
        toks = [t.removeprefix("ال") for t in part.split()]
        if not toks:
            return None
        if len(toks) == 2 and toks[1] in ("عشر", "عشره") and toks[0] in _UNITS:  # 11–19
            total += 10 + _UNITS[toks[0]]
        elif len(toks) == 1 and toks[0] in _TENS:
            total += _TENS[toks[0]]
        elif len(toks) == 1 and toks[0] in _UNITS:
            total += _UNITS[toks[0]]
        else:
            return None
    return total or None


@dataclass
class Mention:
    character_id: uuid.UUID
    node: Node
    doc: Document
    start: int
    end: int


@dataclass
class AgeMention:
    character: Character
    node: Node
    doc: Document
    age: int
    start: int
    end: int


def _name_variants(c: Character) -> list[str]:
    names = [c.canonical_name, *(c.aliases or [])]
    out = []
    for n in names:
        nn, _ = norm_with_map(n.strip())
        if len(nn) >= 2:
            out.append(nn)
    return sorted(set(out), key=len, reverse=True)


def _word_boundary_re(name: str) -> re.Pattern[str]:
    # Allow common proclitics before the name (و، ف، ب، ل، ك) but not letters after it.
    return re.compile(r"(?<![^\W_])(?:[وفبلك])?" + re.escape(name) + r"(?![^\W_])")


def _excerpt(text: str, start: int, end: int, pad: int = 60) -> str:
    s, e = max(0, start - pad), min(len(text), end + pad)
    return ("…" if s > 0 else "") + text[s:e].replace("\n", " ") + ("…" if e < len(text) else "")


def text_evidence(doc: Document, node: Node, label: str, start: int, end: int, note: str = "") -> dict[str, Any]:
    block, off = locate(doc.content_json, start)
    return {
        "kind": "text", "document_id": str(doc.id), "node_id": str(node.id), "label": label,
        "start": start, "end": end, "block": block, "block_offset": off,
        "excerpt": _excerpt(doc.text_plain, start, end), "quote": doc.text_plain[start:end], "note": note,
    }


def entity_evidence(etype: str, eid: uuid.UUID, label: str, field: str, value: Any) -> dict[str, Any]:
    return {"kind": "entity", "entity_type": etype, "entity_id": str(eid), "label": label, "field": field,
            "value": value}


def _story_time(node: Node, parents: dict[uuid.UUID, Node]) -> float | None:
    n: Node | None = node
    while n is not None:
        t = (n.meta or {}).get("story_time")
        if isinstance(t, (int, float)):
            return float(t)
        n = parents.get(n.parent_id) if n.parent_id else None
    return None


class Scan:
    def __init__(self, db: Session, project_id: uuid.UUID):
        self.db = db
        self.project_id = project_id
        self.found: dict[str, dict[str, Any]] = {}
        self.characters = list(db.scalars(select(Character).where(Character.project_id == project_id)))
        self.places = {p.id: p for p in db.scalars(select(Place).where(Place.project_id == project_id))}
        self.events = list(db.scalars(select(Event).where(Event.project_id == project_id)))
        self.facts = list(db.scalars(select(CanonFact).where(CanonFact.project_id == project_id)))
        self.nodes: list[Node] = []
        for m in db.scalars(select(Manuscript).where(Manuscript.project_id == project_id).order_by(Manuscript.position)):
            self.nodes.extend(ordered_nodes(db, m.id))
        self.by_id = {n.id: n for n in self.nodes}
        self.labels = labels(self.nodes)
        docs = db.scalars(select(Document).where(Document.project_id == project_id))
        self.docs = {d.node_id: d for d in docs}
        self.order = {n.id: i for i, n in enumerate(self.nodes)}

    # ── helpers
    def add(self, rule: str, ctype: str, severity: str, title: str, explanation: str,
            evidence: list[dict[str, Any]], key: list[str]) -> None:
        fp = sha256_hex(rule + "|" + "|".join(sorted(key)))
        self.found[fp] = {"rule": rule, "conflict_type": ctype, "severity": severity, "title": title,
                          "explanation": explanation, "evidence": evidence, "fingerprint": fp}

    def char_years(self, c: Character) -> tuple[float | None, float | None]:
        prof = c.profile or {}
        birth = prof.get("birth_year")
        death = prof.get("death_year")
        for e in self.events:
            if str(c.id) in (e.participant_ids or []) and e.story_time_start is not None:
                if e.kind == "birth" and birth is None:
                    birth = e.story_time_start
                if e.kind == "death" and death is None:
                    death = e.story_time_start
        for f in self.facts:
            if f.subject_id == c.id and f.epistemic_status in ("canon", "draft"):
                v = (f.object or {}).get("value")
                if f.predicate in ("birth_year", "سنة الميلاد") and birth is None and isinstance(v, (int, float)):
                    birth = v
                if f.predicate in ("death_year", "سنة الوفاة") and death is None and isinstance(v, (int, float)):
                    death = v
        return (float(birth) if isinstance(birth, (int, float)) else None,
                float(death) if isinstance(death, (int, float)) else None)

    def mentions(self) -> tuple[list[Mention], list[AgeMention]]:
        ments: list[Mention] = []
        ages: list[AgeMention] = []
        variants = [(c, [_word_boundary_re(v) for v in _name_variants(c)]) for c in self.characters]
        for node in self.nodes:
            doc = self.docs.get(node.id)
            if not doc or not doc.text_plain:
                continue
            norm, idx = norm_with_map(doc.text_plain)
            char_spans: list[tuple[int, int, Character]] = []
            for c, pats in variants:
                taken: list[tuple[int, int]] = []
                for pat in pats:
                    for m in pat.finditer(norm):
                        if any(a <= m.start() < b for a, b in taken):
                            continue
                        taken.append((m.start(), m.end()))
                        char_spans.append((m.start(), m.end(), c))
                        ments.append(Mention(c.id, node, doc, idx[m.start()], idx[m.end()]))
            char_spans.sort(key=lambda t: t[0])
            for m in _AGE_RE.finditer(norm):
                age = parse_age(m.group("num"))
                if age is None or age > 130:
                    continue
                # nearest preceding character mention in the same sentence window
                window_start = max(norm.rfind(".", 0, m.start()), norm.rfind("؟", 0, m.start()),
                                   norm.rfind("\n", 0, m.start()), m.start() - 160)
                cands = [t for t in char_spans if window_start <= t[0] < m.start()]
                if not cands:
                    cands = [t for t in char_spans if m.end() <= t[0] < m.end() + 40]
                if not cands:
                    continue
                c = cands[-1][2]
                ages.append(AgeMention(c, node, doc, age, idx[m.start()], idx[m.end()]))
        return ments, ages

    # ── rules
    def run(self) -> dict[str, Any]:
        parents = self.by_id
        ments, ages = self.mentions()
        by_char: dict[uuid.UUID, list[AgeMention]] = {}
        for a in ages:
            by_char.setdefault(a.character.id, []).append(a)

        for lst in by_char.values():
            c = lst[0].character
            birth, _ = self.char_years(c)
            lst.sort(key=lambda a: self.order.get(a.node.id, 0))
            ref: tuple[float, AgeMention] | None = None
            for a in lst:
                t = _story_time(a.node, parents)
                ev_a = text_evidence(a.doc, a.node, self.labels.get(a.node.id, ""), a.start, a.end,
                                     f"العمر المذكور: {a.age}" + (f" · زمن القصة: {t:g}" if t is not None else ""))
                if t is not None:
                    implied = t - a.age
                    if birth is not None and abs(implied - birth) > 1.01:
                        self.add("R-AGE-PROFILE", "age", "high", f"عمر {c.canonical_name} لا يطابق سنة ميلاده",
                                 f"النص يذكر عمر {a.age} في زمن قصة {t:g}، ما يعني ميلاداً نحو {implied:g}، "
                                 f"بينما سنة الميلاد المعتمدة {birth:g}.",
                                 [ev_a, entity_evidence("character", c.id, c.canonical_name, "birth_year", birth)],
                                 [str(c.id), str(a.doc.id), str(a.start)])
                    if ref is None:
                        ref = (implied, a)
                    elif abs(implied - ref[0]) > 1.51:
                        r = ref[1]
                        rt = _story_time(r.node, parents)
                        self.add("R-AGE-PAIR", "age", "high", f"تضارب عمر {c.canonical_name} بين موضعين",
                                 f"في {self.labels.get(r.node.id, '')} عمره {r.age} (زمن {rt:g})، وفي "
                                 f"{self.labels.get(a.node.id, '')} عمره {a.age} (زمن {t:g}) — فرق الميلاد المضمَر "
                                 f"{abs(implied - ref[0]):g} سنة.",
                                 [text_evidence(r.doc, r.node, self.labels.get(r.node.id, ""), r.start, r.end,
                                                f"العمر المذكور: {r.age}"), ev_a],
                                 [str(c.id), str(r.doc.id), str(r.start), str(a.doc.id), str(a.start)])
            # without story time: age decreasing in narration order (possible flashback → low)
            untimed = [a for a in lst if _story_time(a.node, parents) is None]
            for prev, cur in zip(untimed, untimed[1:], strict=False):
                if cur.age < prev.age and prev.node.id != cur.node.id:
                    self.add("R-AGE-ORDER", "age", "low", f"عمر {c.canonical_name} يتناقص مع تقدم السرد",
                             "لا يوجد زمن قصة للمشهدين؛ قد يكون استرجاعاً مقصوداً. حدّد زمن المشهد أو أعفِ التنبيه.",
                             [text_evidence(prev.doc, prev.node, self.labels.get(prev.node.id, ""), prev.start,
                                            prev.end, f"العمر: {prev.age}"),
                              text_evidence(cur.doc, cur.node, self.labels.get(cur.node.id, ""), cur.start, cur.end,
                                            f"العمر: {cur.age}")],
                             [str(c.id), str(prev.doc.id), str(prev.start), str(cur.doc.id), str(cur.start)])

        chars = {c.id: c for c in self.characters}
        # R-DEATH: appearance after death
        for mnt in ments:
            c = chars[mnt.character_id]
            _, death = self.char_years(c)
            t = _story_time(mnt.node, parents)
            if death is None or t is None or t <= death:
                continue
            sent_s = max(mnt.doc.text_plain.rfind(".", 0, mnt.start), mnt.doc.text_plain.rfind("\n", 0, mnt.start))
            sent_e = mnt.doc.text_plain.find(".", mnt.end)
            sentence, _ = norm_with_map(mnt.doc.text_plain[sent_s + 1: sent_e if sent_e > 0 else None])
            if any(mk in sentence for mk in MEMORY_MARKERS):
                continue
            self.add("R-DEATH", "presence", "medium", f"ظهور {c.canonical_name} بعد وفاته",
                     f"زمن المشهد {t:g} لاحق لسنة الوفاة {death:g}. إن كان استرجاعاً أو ذكرى فأعفِ التنبيه مع السبب.",
                     [text_evidence(mnt.doc, mnt.node, self.labels.get(mnt.node.id, ""), mnt.start, mnt.end),
                      entity_evidence("character", c.id, c.canonical_name, "death_year", death)],
                     [str(c.id), str(mnt.node.id)])

        # Events
        for e in self.events:
            s, en = e.story_time_start, e.story_time_end
            if s is not None and en is not None and en < s:
                self.add("R-EVENT-RANGE", "timeline", "high", f"نطاق زمني مقلوب للحدث «{e.title}»",
                         f"بداية الحدث {s:g} بعد نهايته {en:g}.",
                         [entity_evidence("event", e.id, e.title, "story_time_start", s),
                          entity_evidence("event", e.id, e.title, "story_time_end", en)], [str(e.id)])
            if s is None or e.kind in ("birth", "death"):
                continue
            tol = 0.0 if e.uncertainty == "exact" else 1.0
            for pid in e.participant_ids or []:
                try:
                    c = chars.get(uuid.UUID(str(pid)))
                except ValueError:
                    c = None
                if not c:
                    continue
                birth, death = self.char_years(c)
                if birth is not None and s + tol < birth:
                    self.add("R-EVENT-BIRTH", "timeline", "high",
                             f"«{c.canonical_name}» يشارك في «{e.title}» قبل ولادته",
                             f"الحدث مؤرخ بـ {s:g} وسنة الميلاد {birth:g}.",
                             [entity_evidence("event", e.id, e.title, "story_time_start", s),
                              entity_evidence("character", c.id, c.canonical_name, "birth_year", birth)]
                             + self._event_scene_evidence(e), [str(e.id), str(c.id), "birth"])
                if death is not None and s - tol > death:
                    self.add("R-EVENT-DEATH", "timeline", "high",
                             f"«{c.canonical_name}» يشارك في «{e.title}» بعد وفاته",
                             f"الحدث مؤرخ بـ {s:g} وسنة الوفاة {death:g}.",
                             [entity_evidence("event", e.id, e.title, "story_time_start", s),
                              entity_evidence("character", c.id, c.canonical_name, "death_year", death)]
                             + self._event_scene_evidence(e), [str(e.id), str(c.id), "death"])
            if e.node_id and e.node_id in self.by_id:
                node = self.by_id[e.node_id]
                t = _story_time(node, parents)
                end = en if en is not None else s
                if t is not None and not (s - tol - 0.5 <= t <= end + tol + 0.5):
                    self.add("R-EVENT-SCENE", "timeline", "medium",
                             f"زمن المشهد لا يطابق زمن الحدث «{e.title}»",
                             f"المشهد {self.labels.get(node.id, '')} في زمن {t:g} والحدث المرتبط به في {s:g}.",
                             [entity_evidence("event", e.id, e.title, "story_time_start", s),
                              entity_evidence("node", node.id, self.labels.get(node.id, ""), "story_time", t)],
                             [str(e.id), str(node.id)])

        # R-PLACE: same character in two places at the same exact time
        timed = [e for e in self.events if e.story_time_start is not None and e.place_id and e.uncertainty == "exact"]
        for i, a in enumerate(timed):
            for b in timed[i + 1:]:
                if a.place_id == b.place_id or abs((a.story_time_start or 0) - (b.story_time_start or 0)) > 1e-6:
                    continue
                common = set(a.participant_ids or []) & set(b.participant_ids or [])
                for pid in common:
                    c = chars.get(uuid.UUID(str(pid))) if pid else None
                    if not c:
                        continue
                    pa, pb = self.places.get(a.place_id), self.places.get(b.place_id)
                    self.add("R-PLACE", "presence", "medium", f"«{c.canonical_name}» في مكانين في الوقت نفسه",
                             f"«{a.title}» في {pa.name if pa else '؟'} و«{b.title}» في {pb.name if pb else '؟'} "
                             f"كلاهما في {a.story_time_start:g}.",
                             [entity_evidence("event", a.id, a.title, "place", pa.name if pa else ""),
                              entity_evidence("event", b.id, b.title, "place", pb.name if pb else "")],
                             [str(c.id), str(a.id), str(b.id)])

        # R-ALIAS: name collisions between different characters
        seen: dict[str, Character] = {}
        for c in self.characters:
            for v in _name_variants(c):
                other = seen.get(v)
                if other and other.id != c.id:
                    self.add("R-ALIAS", "naming", "medium", f"اسم مشترك بين «{other.canonical_name}» و«{c.canonical_name}»",
                             f"الاسم/الكنية «{v}» مسندة إلى شخصيتين؛ سيلتبس الربط الآلي والقارئ.",
                             [entity_evidence("character", other.id, other.canonical_name, "aliases", v),
                              entity_evidence("character", c.id, c.canonical_name, "aliases", v)],
                             [str(min(other.id, c.id)), str(max(other.id, c.id)), v])
                seen[v] = c

        # R-FACT: contradicting facts (canon/draft) or disagreeing external sources (AT22)
        groups: dict[tuple[str, str], list[CanonFact]] = {}
        for f in self.facts:
            if f.epistemic_status == "hypothesis":
                continue
            groups.setdefault((str(f.subject_id or f.subject_label), f.predicate), []).append(f)
        for (_subj, pred), fs in groups.items():
            for i, a in enumerate(fs):
                for b in fs[i + 1:]:
                    if (a.object or {}).get("value") == (b.object or {}).get("value"):
                        continue
                    if not _overlap(a.valid_from, a.valid_to, b.valid_from, b.valid_to):
                        continue
                    statuses = {a.epistemic_status, b.epistemic_status}
                    if statuses == {"external"}:
                        sev, title = "low", f"المصادر الخارجية تختلف حول «{pred}»"
                        expl = "مصدران يقدمان قيمتين مختلفتين؛ لا يحسم النظام بينهما. اختر أو وثّق الخلاف."
                    else:
                        sev = "high" if statuses == {"canon"} else "medium"
                        title = f"حقيقتان متعارضتان: {a.subject_label or ''} · {pred}".strip()
                        expl = f"«{(a.object or {}).get('value')}» ({a.epistemic_status}) مقابل «{(b.object or {}).get('value')}» ({b.epistemic_status})."
                    self.add("R-FACT", "fact", sev, title, expl,
                             [_fact_evidence(a), _fact_evidence(b)], [str(a.id), str(b.id)])
        return self.found

    def _event_scene_evidence(self, e: Event) -> list[dict[str, Any]]:
        if e.node_id and e.node_id in self.by_id:
            n = self.by_id[e.node_id]
            return [entity_evidence("node", n.id, self.labels.get(n.id, ""), "linked_scene", n.title)]
        return []


def _fact_evidence(f: CanonFact) -> dict[str, Any]:
    ev = entity_evidence("fact", f.id, f.statement or f.predicate, "value", (f.object or {}).get("value"))
    ev["epistemic_status"] = f.epistemic_status
    ev["source_refs"] = f.source_refs or []
    return ev


def _overlap(a1: float | None, a2: float | None, b1: float | None, b2: float | None) -> bool:
    lo_a, hi_a = a1 if a1 is not None else float("-inf"), a2 if a2 is not None else float("inf")
    lo_b, hi_b = b1 if b1 is not None else float("-inf"), b2 if b2 is not None else float("inf")
    return lo_a <= hi_b and lo_b <= hi_a


def run_scan(db: Session, project_id: uuid.UUID) -> dict[str, int]:
    found = Scan(db, project_id).run()
    existing = {c.fingerprint: c for c in db.scalars(select(Conflict).where(Conflict.project_id == project_id))}
    now = utcnow()
    created = reopened = auto_resolved = 0
    for fp, data in found.items():
        c = existing.get(fp)
        if c is None:
            db.add(Conflict(project_id=project_id, last_seen_at=now, **data))
            created += 1
        else:
            c.evidence, c.title, c.explanation, c.severity = data["evidence"], data["title"], data["explanation"], data["severity"]
            c.last_seen_at = now
            if c.state == "resolved":
                c.state, c.resolution_note = "open", "عاد التعارض للظهور بعد فحص جديد."
                reopened += 1
    for fp, c in existing.items():
        if fp not in found and c.state == "open":
            c.state, c.resolution_note, c.resolved_at = "resolved", "لم يعد قائماً في آخر فحص.", now
            auto_resolved += 1
    db.flush()
    return {"found": len(found), "created": created, "reopened": reopened, "auto_resolved": auto_resolved}


def conflict_out(c: Conflict) -> dict[str, Any]:
    return {
        "id": str(c.id), "rule": c.rule, "conflict_type": c.conflict_type, "severity": c.severity, "title": c.title,
        "explanation": c.explanation, "evidence": c.evidence, "state": c.state, "resolution_note": c.resolution_note,
        "resolved_at": c.resolved_at.isoformat() if c.resolved_at else None, "created_at": c.created_at.isoformat(),
        "last_seen_at": c.last_seen_at.isoformat() if c.last_seen_at else None,
    }


__all__ = ["run_scan", "conflict_out", "Scan", "parse_age", "norm_with_map", "block_offsets"]
