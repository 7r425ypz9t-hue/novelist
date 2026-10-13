"""Continuity golden set (ACCEPTANCE_TESTS «مجموعة تقييم أدبية»): 20 planted errors + 20 clean cases.

All sentences are original and written for this benchmark. Each case lives in its own project so that every
alert is attributable. Reports precision / recall and fails below the thresholds recorded in docs.
"""

import uuid

from nis.db import SessionLocal
from nis.models import CanonFact, Character, Event, Manuscript, Membership, Place, Project, User
from nis.security import hash_password
from nis.services.continuity import Scan
from nis.services.manuscript import create_node
from nis.text import doc_from_plain

H = {"name": "هالة", "birth": 1950}
K = {"name": "كمال", "birth": 1940, "death": 1980}

# expect = rule id that MUST fire; None = nothing may fire
CASES = [
    # ── planted errors ──
    dict(id="E01", expect="R-AGE-PROFILE", chars=[H], scenes=[(1970, "كانت هالة في الثلاثين من عمرها حين سافرت.")]),
    dict(id="E02", expect="R-AGE-PROFILE", chars=[H], scenes=[(1960, "بلغت هالة خمسة عشر عاماً في ذلك الصيف.")]),
    dict(id="E03", expect="R-AGE-PAIR", chars=[{"name": "هالة"}], scenes=[
        (1960, "كانت هالة في العاشرة من عمرها."), (1970, "كانت هالة في الخامسة والعشرين من عمرها.")]),
    dict(id="E04", expect="R-AGE-PAIR", chars=[{"name": "كمال"}], scenes=[
        (1950, "كان كمال ابن 12 عاماً."), (1955, "كان كمال ابن 30 عاماً.")]),
    dict(id="E05", expect="R-AGE-ORDER", chars=[{"name": "هالة"}], scenes=[
        (None, "كانت هالة في الأربعين من عمرها."), (None, "كانت هالة في العشرين من عمرها.")]),
    dict(id="E06", expect="R-DEATH", chars=[K], scenes=[(1985, "دخل كمال المقهى وطلب قهوته المعتادة.")]),
    dict(id="E07", expect="R-DEATH", chars=[K], scenes=[(1990, "وقف كمال عند النافذة ينتظر المطر.")]),
    dict(id="E08", expect="R-EVENT-BIRTH", chars=[H], events=[{"title": "الرحلة", "t": 1945, "who": [0]}]),
    dict(id="E09", expect="R-EVENT-BIRTH", chars=[K], events=[{"title": "العرس", "t": 1930, "who": [0]}]),
    dict(id="E10", expect="R-EVENT-DEATH", chars=[K], events=[{"title": "الانتخابات", "t": 1985, "who": [0]}]),
    dict(id="E11", expect="R-EVENT-DEATH", chars=[K], events=[{"title": "الحفل", "t": 1999, "who": [0]}]),
    dict(id="E12", expect="R-EVENT-SCENE", chars=[H], scenes=[(1980, "مرّ النهار هادئاً.")],
         events=[{"title": "العاصفة", "t": 1970, "scene": 0}]),
    dict(id="E13", expect="R-EVENT-SCENE", chars=[H], scenes=[(1965, "جاء الخبر في المساء.")],
         events=[{"title": "الحريق", "t": 1975, "scene": 0}]),
    dict(id="E14", expect="R-EVENT-RANGE", chars=[H], events=[{"title": "الحصار", "t": 1970, "end": 1968}]),
    dict(id="E15", expect="R-PLACE", chars=[H], places=["المرفأ", "السوق"], events=[
        {"title": "لقاء", "t": 1975, "who": [0], "place": 0}, {"title": "شراء", "t": 1975, "who": [0], "place": 1}]),
    dict(id="E16", expect="R-ALIAS", chars=[{"name": "هالة", "aliases": ["أم سعيد"]},
                                            {"name": "نوال", "aliases": ["أم سعيد"]}]),
    dict(id="E17", expect="R-ALIAS", chars=[{"name": "كمال"}, {"name": "كمال"}]),
    dict(id="E18", expect="R-FACT", facts=[("لون البيت", "أزرق", "canon"), ("لون البيت", "أبيض", "canon")]),
    dict(id="E19", expect="R-FACT", facts=[("سنة التأسيس", 1932, "external"), ("سنة التأسيس", 1934, "external")]),
    dict(id="E20", expect="R-AGE-PROFILE", chars=[{"name": "هالة", "birth": 1950, "aliases": ["أم سعيد"]}],
         scenes=[(1990, "كانت أم سعيد في الستين من عمرها.")]),
    # ── clean cases (no alert expected) ──
    dict(id="C01", expect=None, chars=[H], scenes=[(1970, "كانت هالة في العشرين من عمرها حين سافرت.")]),
    dict(id="C02", expect=None, chars=[{"name": "هالة"}], scenes=[
        (1960, "كانت هالة في العاشرة من عمرها."), (1975, "كانت هالة في الخامسة والعشرين من عمرها.")]),
    dict(id="C03", expect=None, chars=[{"name": "هالة"}], scenes=[
        (None, "كانت هالة في العشرين من عمرها."), (None, "كانت هالة في الأربعين من عمرها.")]),
    dict(id="C04", expect=None, chars=[K], scenes=[(1985, "تذكّرت أمه كمال وهي تطوي ثيابه القديمة.")]),
    dict(id="C05", expect=None, chars=[K], scenes=[(1990, "زار الأبناء قبر كمال في الصباح.")]),
    dict(id="C06", expect=None, chars=[K], scenes=[(1975, "دخل كمال المقهى وطلب قهوته المعتادة.")]),
    dict(id="C07", expect=None, chars=[H], events=[{"title": "الرحلة", "t": 1960, "who": [0]}]),
    dict(id="C08", expect=None, chars=[K], events=[{"title": "وفاة كمال", "t": 1980, "who": [0], "kind": "death"}]),
    dict(id="C09", expect=None, chars=[H], events=[{"title": "الرحلة", "t": 1949.5, "who": [0], "unc": "approx"}]),
    dict(id="C10", expect=None, chars=[H], scenes=[(1970, "مرّ النهار هادئاً.")],
         events=[{"title": "العاصفة", "t": 1970, "scene": 0}]),
    dict(id="C11", expect=None, chars=[H], scenes=[(1971, "جاء الخبر في المساء.")],
         events=[{"title": "الحريق", "t": 1970, "scene": 0, "unc": "approx"}]),
    dict(id="C12", expect=None, chars=[H], events=[{"title": "الحصار", "t": 1968, "end": 1970}]),
    dict(id="C13", expect=None, chars=[H], places=["المرفأ", "السوق"], events=[
        {"title": "لقاء", "t": 1975, "who": [0], "place": 0}, {"title": "شراء", "t": 1976, "who": [0], "place": 1}]),
    dict(id="C14", expect=None, chars=[{"name": "هالة"}, {"name": "نوال"}]),
    dict(id="C15", expect=None, facts=[("لون البيت", "أزرق", "canon"), ("لون البيت", "أبيض", "hypothesis")]),
    dict(id="C16", expect=None, facts=[("سنة التأسيس", 1932, "external"), ("سنة التأسيس", 1932, "external")]),
    dict(id="C17", expect=None, chars=[H], scenes=[(1970, "كان البيت في المئة من عمره، وهالة تسكنه وحدها.")]),
    dict(id="C18", expect=None, chars=[H], scenes=[(1970, "قالت هالة إن جدها عاش طويلاً.")]),
    dict(id="C19", expect=None, chars=[{"name": "هالة", "birth": 1950, "aliases": ["أم سعيد"]}],
         scenes=[(1990, "كانت أم سعيد في الأربعين من عمرها.")]),
    dict(id="C20", expect=None, facts=[("لون البيت", "أزرق", "canon", None, 1960), ("لون البيت", "أبيض", "canon", 1961, None)]),
]


def _run_case(db, owner_id, case):
    p = Project(owner_id=owner_id, title=case["id"])
    db.add(p)
    db.flush()
    db.add(Membership(user_id=owner_id, project_id=p.id, role="owner"))
    m = Manuscript(project_id=p.id, title=case["id"])
    db.add(m)
    db.flush()
    chars = []
    for c in case.get("chars", []):
        prof = {k: v for k, v in (("birth_year", c.get("birth")), ("death_year", c.get("death"))) if v is not None}
        ch = Character(project_id=p.id, canonical_name=c["name"], aliases=c.get("aliases", []), profile=prof)
        db.add(ch)
        chars.append(ch)
    places = []
    for name in case.get("places", []):
        pl = Place(project_id=p.id, name=name)
        db.add(pl)
        places.append(pl)
    db.flush()
    nodes = []
    for t, text in case.get("scenes", []):
        meta = {"story_time": t} if t is not None else {}
        nodes.append(create_node(db, manuscript=m, parent=None, node_type="chapter", title="", position=None,
                                 user_id=owner_id, content=doc_from_plain(text), meta=meta))
    for e in case.get("events", []):
        db.add(Event(project_id=p.id, title=e["title"], story_time_start=e["t"], story_time_end=e.get("end"),
                     uncertainty=e.get("unc", "exact"), kind=e.get("kind", "event"),
                     participant_ids=[str(chars[i].id) for i in e.get("who", [])],
                     place_id=places[e["place"]].id if "place" in e else None,
                     node_id=nodes[e["scene"]].id if "scene" in e else None))
    for f in case.get("facts", []):
        pred, val, status = f[0], f[1], f[2]
        vf = f[3] if len(f) > 3 else None
        vt = f[4] if len(f) > 4 else None
        db.add(CanonFact(project_id=p.id, subject_type="world", subject_label="البيت", predicate=pred,
                         object={"value": val}, epistemic_status=status, valid_from=vf, valid_to=vt))
    db.flush()
    found = Scan(db, p.id).run()
    return {v["rule"] for v in found.values()}


def test_continuity_golden_set_precision_recall(capsys):
    db = SessionLocal()
    try:
        u = User(email=f"bench-{uuid.uuid4().hex[:6]}@example.test", password_hash=hash_password("x" * 12))
        db.add(u)
        db.flush()
        tp = fn = fp = tn = 0
        misses, false_alarms = [], []
        for case in CASES:
            rules = _run_case(db, u.id, case)
            if case["expect"]:
                if case["expect"] in rules:
                    tp += 1
                else:
                    fn += 1
                    misses.append((case["id"], case["expect"], sorted(rules)))
                # any extra, unrelated rule on an error case also counts as a false alarm
                extra = rules - {case["expect"], "R-AGE-PAIR", "R-AGE-PROFILE"}
                if extra:
                    fp += len(extra)
                    false_alarms.append((case["id"], sorted(extra)))
            else:
                if rules:
                    fp += len(rules)
                    false_alarms.append((case["id"], sorted(rules)))
                else:
                    tn += 1
        db.rollback()
    finally:
        db.close()
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    with capsys.disabled():
        print(f"\ncontinuity golden set: TP={tp} FN={fn} FP={fp} TN={tn} "
              f"precision={precision:.2f} recall={recall:.2f} misses={misses} false_alarms={false_alarms}")
    assert recall >= 0.95, misses
    assert precision >= 0.90, false_alarms
