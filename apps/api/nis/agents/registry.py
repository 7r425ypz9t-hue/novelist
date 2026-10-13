"""Agent and skill registry (AGENTS.md, SYSTEM_SPEC §3) — the single source of truth used by the
orchestrator, the API and the control panel.

`mode`: deterministic = works fully offline; hybrid = deterministic core + optional model enrichment;
model = needs an enabled provider (otherwise returns an explicit "requires provider" result, never fake output).
"""

from typing import Any

SKILLS: dict[str, dict[str, Any]] = {
    "SK01": {"name": "توليد الفكرة والأطروحة والصراع", "risk": "LOW", "mode": "hybrid"},
    "SK02": {"name": "تصميم الحبكة والبنية", "risk": "LOW", "mode": "deterministic"},
    "SK03": {"name": "الشخصيات وأقواس التحول", "risk": "LOW", "mode": "deterministic"},
    "SK04": {"name": "العالم الروائي", "risk": "LOW", "mode": "deterministic"},
    "SK05": {"name": "الخط الزمني", "risk": "LOW", "mode": "deterministic"},
    "SK06": {"name": "الراوي والتبئير", "risk": "LOW", "mode": "deterministic"},
    "SK07": {"name": "الحوار والنص المضمر", "risk": "LOW", "mode": "deterministic"},
    "SK08": {"name": "البصمة الأسلوبية (LSIS)", "risk": "LOW", "mode": "deterministic"},
    "SK09": {"name": "الرموز والموتيفات", "risk": "LOW", "mode": "deterministic"},
    "SK10": {"name": "بناء المشهد", "risk": "LOW", "mode": "deterministic"},
    "SK11": {"name": "الإيقاع والتوتر", "risk": "LOW", "mode": "deterministic"},
    "SK12": {"name": "العمق النفسي والفلسفي", "risk": "LOW", "mode": "model"},
    "SK13": {"name": "البحث والتثبت التاريخي", "risk": "LOW", "mode": "deterministic"},
    "SK14": {"name": "النقد البنيوي", "risk": "LOW", "mode": "hybrid"},
    "SK15": {"name": "التحرير التطويري والأسلوبي واللغوي", "risk": "MEDIUM", "mode": "hybrid"},
    "SK16": {"name": "الاستمرارية", "risk": "LOW", "mode": "deterministic"},
    "SK17": {"name": "التأثير الوجداني", "risk": "LOW", "mode": "deterministic"},
    "SK18": {"name": "محاكاة القراءة (افتراضية)", "risk": "LOW", "mode": "deterministic"},
    "SK19": {"name": "الأصالة والأخلاقيات والحقوق", "risk": "LOW", "mode": "deterministic"},
    "SK20": {"name": "إخراج النشر", "risk": "LOW", "mode": "deterministic"},
    # Improvement (docs/SPEC_REVIEW.md §3.2): A08 had no skill in the spec.
    "SK21": {"name": "أمانة الذاكرة واقتراح الحقائق", "risk": "MEDIUM", "mode": "deterministic"},
}

AGENTS: dict[str, dict[str, Any]] = {
    "A00": {"name": "رئيس التحرير الروائي", "role": "تخطيط المهمة وتوزيع المهارات وتجميع النتائج دون تغيير النص",
            "skills": []},
    "A01": {"name": "مهندس الحبكة", "role": "مخططات واقتراحات بنيوية، لا يحذف أي مشهد",
            "skills": ["SK01", "SK02", "SK10", "SK11"]},
    "A02": {"name": "خبير الشخصيات", "role": "أقواس التحول والتناقضات والبدائل", "skills": ["SK03", "SK17"]},
    "A03": {"name": "مهندس العالم والزمن", "role": "العالم والتسلسل وشبكة الرموز المقترحة",
            "skills": ["SK04", "SK05", "SK09"]},
    "A04": {"name": "مستشار الأسلوب والحوار", "role": "يحمي البصمة الأسلوبية ولا يقلد مؤلفاً خارج المشروع",
            "skills": ["SK06", "SK07", "SK08"]},
    "A05": {"name": "الباحث التاريخي", "role": "يبحث في المصادر المرخصة؛ عدم المعرفة = غير متحقق",
            "skills": ["SK13"]},
    "A06": {"name": "مستشار العمق الفكري والنفسي", "role": "يختبر المعقولية دون تشخيص أو فرض فلسفة",
            "skills": ["SK12", "SK17"]},
    "A07": {"name": "مراقب الاستمرارية", "role": "يفحص الكانون والزمن والأسماء؛ كل تنبيه بشاهدين",
            "skills": ["SK16"]},
    "A08": {"name": "أمين الذاكرة الروائية", "role": "إدارة الحقائق وحالاتها؛ التحويل إلى كانون بموافقة",
            "skills": ["SK21"]},
    "A09": {"name": "الناقد البنيوي المضاد", "role": "اعتراضات بديلة تميّز الذوقي من الموضوعي",
            "skills": ["SK14"]},
    "A10": {"name": "المحرر الأدبي", "role": "فروق لا استبدال؛ يشرح أثر كل تعديل", "skills": ["SK15"]},
    "A11": {"name": "المدقق اللغوي", "role": "ترقيم وإملاء ومطابقة؛ لا يحوّل العامية إلى فصحى",
            "skills": ["SK15"]},
    "A12": {"name": "مراجع الأصالة والنشر", "role": "التشابه والترخيص والإخراج والبيانات الوصفية",
            "skills": ["SK18", "SK19", "SK20"]},
}

# Handoff order used by A00 (AGENTS.md «تسليم المهام»). A06 was missing from the spec's handoff chain;
# it joins the parallel planning stage (docs/SPEC_REVIEW.md §3.2).
PIPELINE: list[list[str]] = [["A08"], ["A01", "A02", "A03", "A04", "A06"], ["A07"], ["A05"], ["A09"], ["A10", "A11"], ["A12"]]

# Capability model: these are the ONLY tools an agent context exposes. Forbidden tools are not merely
# denied — they do not exist on the object handed to skills (see orchestrator.ToolContext).
AGENT_TOOLS = {"read_project", "read_revision", "search_canon", "retrieve_sources", "create_proposal"}
FORBIDDEN_TOOLS = {"accept_proposal", "modify_canon", "delete_project", "external_publish", "shell_access"}

NLQI_DEFAULT_WEIGHTS = {
    "originality": 15, "plot": 15, "characters": 15, "style": 15, "depth": 10,
    "dialogue": 8, "rhythm": 7, "continuity": 5, "impact": 5, "verification": 5,
}
NLQI_LABELS = {
    "originality": "الأصالة", "plot": "الحبكة", "characters": "الشخصيات", "style": "الأسلوب", "depth": "العمق",
    "dialogue": "الحوار", "rhythm": "الإيقاع", "continuity": "الاستمرارية", "impact": "التأثير",
    "verification": "التحقق",
}


def skills_for(agent_id: str) -> list[str]:
    return list(AGENTS[agent_id]["skills"])


def catalog() -> dict[str, Any]:
    return {
        "agents": [{"id": k, **v} for k, v in AGENTS.items()],
        "skills": [{"id": k, **v, "agents": [a for a, d in AGENTS.items() if k in d["skills"]],
                    "requires_author_approval": True} for k, v in SKILLS.items()],
        "pipeline": PIPELINE,
        "tools": {"allowed": sorted(AGENT_TOOLS), "forbidden": sorted(FORBIDDEN_TOOLS)},
    }
