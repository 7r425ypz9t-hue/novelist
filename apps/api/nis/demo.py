"""Original demo content written for this project (no third-party text). It deliberately contains a few
continuity and punctuation issues so the control panel has something real to show."""

from sqlalchemy import select

from .db import SessionLocal
from .models import Character, Event, Manuscript, Membership, Place, Project, User
from .security import hash_password
from .services.manuscript import create_node
from .text import doc_from_plain

DEMO_EMAIL = "demo@nis.local"
DEMO_PASSWORD = "demo-password-2026"

CH1_S1 = """كانت الريح تأتي من جهة البحر محمّلةً برائحة الملح والخشب المبلول، وكان «سالم» يقف عند باب الدكان يعدّ السفن العائدة واحدةً واحدة.

كان سالم في الثانية عشرة من عمره حين رأى البحر يبتلع قارب أبيه, ولم يبكِ يومها، بل جلس على الرصيف حتى الفجر ينتظر شيئاً لا اسم له.

قالت أمه وهي تطوي الشباك: «البحر لا يعيد ما يأخذه يا ولدي?»

قالت أمه وهي تطوي الشباك: «البحر لا يعيد ما يأخذه يا ولدي?»

في عام 1958 افتُتح الميناء الجديد على الضفة الشمالية، وتبدّلت حياة الصيادين في الحيّ كله."""

CH1_S2 = """في المساء جاءت «مريم» تحمل سلّة التمر، ووقفت عند العتبة لا تدخل ولا تعود.

قالت: «سمعتُ أن المركب الكبير سيرحل غداً إلى البصرة» ثم سكتت سكوتاً طويلاً.

لم يجب سالم. كان ينظر إلى الأفق كمن يقرأ سطراً كتبه الموج في في الماء."""

CH2_S1 = """مرّت السنوات كما تمرّ القوارب الصغيرة بين الصخور: بحذرٍ، وبلا شهود.

كان سالم في الخامسة والعشرين من عمره حين عاد إلى الميناء رباناً لمركبٍ لم يكن يملكه.. ولم يكن يحلم به.

وقف حيث كانت أمه تطوي الشباك، فلم يجد إلا مسماراً صدئاً في الجدار وظلّاً لا يشبه أحداً."""


def load_demo() -> str:
    db = SessionLocal()
    try:
        u = db.scalar(select(User).where(User.email == DEMO_EMAIL))
        if u is None:
            u = User(email=DEMO_EMAIL, display_name="كاتب تجريبي", password_hash=hash_password(DEMO_PASSWORD))
            db.add(u)
            db.flush()
        p = Project(owner_id=u.id, title="ملح الضفة الشمالية", genre="رواية اجتماعية", word_goal=60000,
                    logline="صبيٌّ يفقد أباه في البحر ثم يعود إليه رباناً ليكتشف أن الميناء لم يعد يعرفه.",
                    description="مشروع تجريبي أصلي لعرض قدرات الاستوديو.")
        db.add(p)
        db.flush()
        db.add(Membership(user_id=u.id, project_id=p.id, role="owner"))
        m = Manuscript(project_id=p.id, title=p.title, author_name="كاتب تجريبي")
        db.add(m)
        db.flush()
        salem = Character(project_id=p.id, canonical_name="سالم", aliases=["أبو البحر"],
                          profile={"birth_year": 1945, "goal": "أن يستعيد مكانه في الميناء", "role": "بطل"})
        maryam = Character(project_id=p.id, canonical_name="مريم", profile={"role": "رفيقة الطفولة"})
        port = Place(project_id=p.id, name="الميناء الشمالي", profile={"description": "ميناء صيادين على الضفة الشمالية"})
        db.add_all([salem, maryam, port])
        db.flush()
        ch1 = create_node(db, manuscript=m, parent=None, node_type="chapter", title="البحر الذي لا يعيد", position=None,
                          user_id=u.id)
        create_node(db, manuscript=m, parent=ch1, node_type="scene", title="الغرق", position=None, user_id=u.id,
                    content=doc_from_plain(CH1_S1),
                    meta={"story_time": 1957, "goal": "تقديم الفقد", "conflict": "الصبي والبحر",
                          "outcome": "انكسار الطفولة", "pov_character_id": str(salem.id), "place_id": str(port.id)})
        create_node(db, manuscript=m, parent=ch1, node_type="scene", title="سلة التمر", position=None, user_id=u.id,
                    content=doc_from_plain(CH1_S2), meta={"story_time": 1957})
        ch2 = create_node(db, manuscript=m, parent=None, node_type="chapter", title="العودة", position=None,
                          user_id=u.id)
        s3 = create_node(db, manuscript=m, parent=ch2, node_type="scene", title="الربان", position=None, user_id=u.id,
                         content=doc_from_plain(CH2_S1), meta={"story_time": 1972})
        db.add(Event(project_id=p.id, title="غرق قارب الأب", story_time_start=1957, narration_order=1,
                     participant_ids=[str(salem.id)], place_id=port.id))
        db.add(Event(project_id=p.id, title="عودة سالم رباناً", story_time_start=1972, narration_order=2,
                     participant_ids=[str(salem.id)], place_id=port.id, node_id=s3.id))
        db.commit()
        return f"demo project created: {p.id} — login {DEMO_EMAIL} / {DEMO_PASSWORD}"
    finally:
        db.close()
