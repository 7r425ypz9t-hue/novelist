"""Hijri ↔ Gregorian (tabular) for story time."""

from datetime import date

from nis.calendars import convert, gregorian_to_hijri, hijri_to_gregorian


def _close(a: date, b: date, days: int = 2) -> bool:
    return abs((a - b).days) <= days


def test_known_hijri_dates_within_two_days():
    assert _close(hijri_to_gregorian(1446, 1, 1), date(2024, 7, 7))
    assert _close(hijri_to_gregorian(1445, 9, 1), date(2024, 3, 11))
    assert _close(hijri_to_gregorian(1, 1, 1), date(622, 7, 19), 3)


def test_roundtrip():
    for d in (date(1957, 7, 28), date(2000, 1, 1), date(1900, 3, 15)):
        y, m, dd = gregorian_to_hijri(d)
        assert hijri_to_gregorian(y, m, dd) == d


def test_year_only_is_approximate_midpoint(writer):
    r = convert("hijri", 1377)
    assert r["uncertainty"] == "approx" and 1957.9 < r["story_time"] < 1958.2 and r["label"] == "1377 هـ"
    p = writer.project()
    api = writer.get(f"/v1/projects/{p['id']}/calendar/convert", params={"calendar": "hijri", "year": 1377, "month": 9, "day": 1}).json()
    assert api["uncertainty"] == "exact" and api["label"] == "1 رمضان 1377 هـ" and "يوماً أو يومين" in api["note"]
    assert writer.get(f"/v1/projects/{p['id']}/calendar/convert", params={"calendar": "hijri", "year": 1377, "month": 13}).status_code == 400


def test_fictional_world_calendar(writer):
    p = writer.project()
    cal = {"id": "flood", "name": "تقويم الطوفان", "suffix": "ط", "epoch": 1200, "ratio": 2,
           "months": ["الندى", "الريح", "الملح", "الرماد"]}
    assert writer.put(f"/v1/projects/{p['id']}/calendars", json={"calendars": [cal]}).status_code == 200
    r = writer.get(f"/v1/projects/{p['id']}/calendar/convert", params={"calendar": "flood", "year": 10, "month": 3}).json()
    assert r["label"] == "الملح 10 ط" and r["story_time"] == 1200 + (9 + 0.5) * 2 and r["uncertainty"] == "exact"
    assert writer.get(f"/v1/projects/{p['id']}/calendar/convert", params={"calendar": "flood", "year": 1, "month": 9}).status_code == 400
    assert writer.put(f"/v1/projects/{p['id']}/calendars", json={"calendars": [{**cal, "id": "hijri"}]}).status_code == 400
    assert writer.get(f"/v1/projects/{p['id']}/calendars").json()["custom"][0]["name"] == "تقويم الطوفان"
