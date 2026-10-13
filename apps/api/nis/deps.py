"""Authentication and row-level authorization helpers.

Every project-scoped endpoint resolves access through `ProjectAccess`, which returns 404 (not 403) to
non-members so that object existence never leaks across projects (NFR05, AT12).
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .errors import ProblemError, forbidden, not_found
from .models import AuthSession, Document, Membership, Node, Project, User
from .security import token_digest

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "owner": {
        "read", "comment", "write", "bible", "run_agents", "decide_proposals", "approve_canon",
        "sources", "export", "manage", "delete",
    },
    "editor": {"read", "comment", "write", "bible", "run_agents", "sources", "export"},
    "commenter": {"read", "comment"},
    "reader": {"read", "comment"},
}


def current_user(
    authorization: str | None = Header(default=None), db: Session = Depends(get_db)
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise ProblemError(401, "غير مصادق", "سجّل الدخول للمتابعة.", "/problems/unauthenticated")
    digest = token_digest(authorization.split(" ", 1)[1].strip())
    sess = db.scalar(select(AuthSession).where(AuthSession.token_hash == digest))
    now = datetime.now(UTC)
    if not sess or sess.revoked_at is not None or _aware(sess.expires_at) < now:
        raise ProblemError(401, "غير مصادق", "انتهت الجلسة أو أنها غير صالحة.", "/problems/unauthenticated")
    user = db.get(User, sess.user_id)
    if not user or not user.is_active:
        raise ProblemError(401, "غير مصادق", "الحساب غير نشط.", "/problems/unauthenticated")
    return user


def admin_user(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise forbidden("هذه العملية مخصصة لمسؤول النظام.")
    return user


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


@dataclass
class Access:
    user: User
    project: Project
    role: str
    perms: set[str]

    def require(self, perm: str) -> "Access":
        if perm not in self.perms:
            raise forbidden(_PERM_MSG.get(perm, "لا تملك الصلاحية اللازمة لهذه العملية."))
        return self


_PERM_MSG = {
    "write": "دورك في المشروع لا يسمح بتعديل المخطوط.",
    "decide_proposals": "اعتماد المقترحات أو رفضها حق لصاحب الرواية وحده.",
    "approve_canon": "اعتماد الحقائق في الكانون حق لصاحب الرواية وحده.",
    "manage": "إدارة المشروع حق لصاحب الرواية وحده.",
    "delete": "حذف المشروع حق لصاحب الرواية وحده.",
}


def access_for(db: Session, user: User, project_id: uuid.UUID) -> Access:
    project = db.get(Project, project_id)
    if not project:
        raise not_found("المشروع")
    m = db.scalar(select(Membership).where(Membership.project_id == project_id, Membership.user_id == user.id))
    if not m:
        raise not_found("المشروع")
    perms = set(ROLE_PERMISSIONS.get(m.role, set()))
    extra: dict[str, Any] = m.permissions or {}
    perms |= {p for p, granted in extra.items() if granted is True and p in ROLE_PERMISSIONS["editor"]}
    return Access(user=user, project=project, role=m.role, perms=perms)


def project_access(
    project_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> Access:
    return access_for(db, user, project_id)


def node_access(db: Session, user: User, node_id: uuid.UUID) -> tuple[Node, Access]:
    node = db.get(Node, node_id)
    if not node:
        raise not_found("العقدة")
    return node, access_for(db, user, node.project_id)


def document_access(db: Session, user: User, document_id: uuid.UUID) -> tuple[Document, Access]:
    doc = db.get(Document, document_id)
    if not doc:
        raise not_found("المستند")
    return doc, access_for(db, user, doc.project_id)
