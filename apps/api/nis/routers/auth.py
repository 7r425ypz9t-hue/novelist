from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import audit
from ..config import get_settings
from ..db import get_db
from ..deps import current_user
from ..errors import ProblemError, conflict, forbidden
from ..models import AuthSession, User
from ..schemas import LoginIn, RegisterIn
from ..security import hash_password, new_token, token_digest, verify_password

router = APIRouter(prefix="/v1/auth", tags=["auth"])


def user_out(u: User) -> dict:
    return {"id": str(u.id), "email": u.email, "display_name": u.display_name, "is_admin": u.is_admin,
            "settings": u.settings or {}}


def _issue(db: Session, user: User, ua: str) -> str:
    token = new_token()
    db.add(AuthSession(user_id=user.id, token_hash=token_digest(token), user_agent=ua[:300],
                       expires_at=datetime.now(UTC) + timedelta(days=get_settings().session_days)))
    return token


@router.post("/register", status_code=201)
def register(body: RegisterIn, request: Request, db: Session = Depends(get_db)):
    s = get_settings()
    if not s.allow_registration:
        raise forbidden("التسجيل مغلق على هذا الخادم.")
    if db.scalar(select(User).where(User.email == body.email)):
        raise conflict("هذا البريد مسجّل مسبقاً.")
    first = (db.scalar(select(func.count()).select_from(User)) or 0) == 0
    u = User(email=body.email, display_name=body.display_name or body.email.split("@")[0],
             password_hash=hash_password(body.password), is_admin=first and s.first_user_is_admin)
    db.add(u)
    db.flush()
    token = _issue(db, u, request.headers.get("user-agent", ""))
    audit.record(db, "auth.register", actor_id=u.id, object_type="user", object_id=u.id)
    db.commit()
    return {"token": token, "user": user_out(u)}


@router.post("/login")
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    u = db.scalar(select(User).where(User.email == body.email.strip().lower()))
    if not u or not u.is_active or not verify_password(body.password, u.password_hash):
        audit.record(db, "auth.login_failed", actor_id=u.id if u else None, meta={"email_known": bool(u)})
        db.commit()
        raise ProblemError(401, "بيانات الدخول غير صحيحة", "تحقق من البريد وكلمة المرور.", "/problems/bad-credentials")
    token = _issue(db, u, request.headers.get("user-agent", ""))
    audit.record(db, "auth.login", actor_id=u.id, object_type="user", object_id=u.id)
    db.commit()
    return {"token": token, "user": user_out(u)}


@router.post("/logout", status_code=204)
def logout(authorization: str = Header(), db: Session = Depends(get_db), user: User = Depends(current_user)):
    sess = db.scalar(select(AuthSession).where(AuthSession.token_hash == token_digest(authorization.split(" ", 1)[1])))
    if sess:
        sess.revoked_at = datetime.now(UTC)
        db.commit()


@router.get("/me")
def me(user: User = Depends(current_user)):
    return user_out(user)
