"""Calendar conversion for story time (docs/SPEC_REVIEW.md R4).

Story time is stored as a decimal Gregorian year so every rule compares on one axis; the author's original
calendar and wording are kept in the label. Hijri uses the arithmetic (tabular, civil epoch) calendar, which can
differ from sighting-based dates by ±1–2 days — the response says so explicitly.
"""

from datetime import date, timedelta

_ISLAMIC_EPOCH_JD = 1948439.5  # 1 Muharram 1 AH (civil), Julian Day


def _jd_from_gregorian(y: int, m: int, d: int) -> float:
    return date(y, m, d).toordinal() + 1721424.5


def _gregorian_from_jd(jd: float) -> date:
    return date.fromordinal(int(jd - 1721424.5))


def hijri_to_jd(year: int, month: int = 1, day: int = 1) -> float:
    return (day + -(-(29.5 * (month - 1)) // 1) + (year - 1) * 354 + (3 + 11 * year) // 30
            + _ISLAMIC_EPOCH_JD - 1)


def hijri_to_gregorian(year: int, month: int = 1, day: int = 1) -> date:
    if not (1 <= month <= 12 and 1 <= day <= 30 and year >= 1):
        raise ValueError("تاريخ هجري غير صالح")
    return _gregorian_from_jd(hijri_to_jd(year, month, day))


def gregorian_to_hijri(d: date) -> tuple[int, int, int]:
    jd = _jd_from_gregorian(d.year, d.month, d.day)
    year = int((30 * (jd - _ISLAMIC_EPOCH_JD) + 10646) // 10631)
    month = int(min(12, -(-((jd - (29 + hijri_to_jd(year, 1, 1))) / 29.5) // 1) + 1))
    day = int(jd - hijri_to_jd(year, month, 1) + 1)
    return year, month, day


def decimal_year(d: date) -> float:
    start = date(d.year, 1, 1)
    days = (date(d.year + 1, 1, 1) - start).days
    return round(d.year + (d - start).days / days, 4)


HIJRI_MONTHS = ["محرم", "صفر", "ربيع الأول", "ربيع الآخر", "جمادى الأولى", "جمادى الآخرة", "رجب", "شعبان",
                "رمضان", "شوال", "ذو القعدة", "ذو الحجة"]


def convert_custom(cal: dict, year: float, month: int | None = None) -> dict:
    """A fictional calendar maps linearly onto the story axis: axis = epoch + (year - 1 + month_fraction) × ratio.
    `epoch` is the axis year of «year 1», `ratio` how many axis years one calendar year lasts."""
    months = cal.get("months") or []
    if month is not None and months and not 1 <= month <= len(months):
        raise ValueError("رقم الشهر خارج تقويم هذا العالم")
    frac = ((month - 1) / len(months)) if (month and months) else 0.5
    axis = float(cal.get("epoch", 0)) + (year - 1 + frac) * float(cal.get("ratio", 1) or 1)
    y = int(year) if float(year).is_integer() else year
    label = (f"{months[month - 1]} {y} {cal.get('suffix', '')}" if month and months else f"{y} {cal.get('suffix', '')}").strip()
    return {"story_time": round(axis, 4), "gregorian": None, "label": label,
            "uncertainty": "exact" if month else "approx",
            "note": f"تقويم «{cal.get('name', '')}»: سنة 1 = {cal.get('epoch', 0)} على محور القصة، كل سنة = {cal.get('ratio', 1)}."}


def convert(calendar: str, year: int, month: int | None = None, day: int | None = None,
            custom: list[dict] | None = None) -> dict:
    for cal in custom or []:
        if cal.get("id") == calendar:
            return convert_custom(cal, year, month)
    if calendar == "hijri":
        g = hijri_to_gregorian(year, month or 1, day or 1)
        label = f"{day} {HIJRI_MONTHS[(month or 1) - 1]} {year} هـ" if day and month else (
            f"{HIJRI_MONTHS[month - 1]} {year} هـ" if month else f"{year} هـ")
        # year-only input spans ~354 days: report the midpoint and mark it approximate
        if month is None:
            g = g + timedelta(days=177)
        return {"story_time": decimal_year(g), "gregorian": g.isoformat(), "label": label,
                "uncertainty": "exact" if day else "approx",
                "note": "تحويل حسابي (التقويم الهجري الجدولي) قد يختلف يوماً أو يومين عن الرؤية."}
    if calendar == "gregorian":
        g = date(year, month or 1, day or 1)
        if month is None:
            g = date(year, 7, 2)
        return {"story_time": decimal_year(g), "gregorian": g.isoformat(),
                "label": f"{year}" if month is None else g.isoformat(),
                "uncertainty": "exact" if day else "approx", "note": ""}
    raise ValueError("تقويم غير مدعوم")
