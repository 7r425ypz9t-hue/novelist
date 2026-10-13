import uuid
from typing import Any

from sqlalchemy.orm import Session

from .models import AuditEvent

# Keys that may carry manuscript or personal content are never written to the audit log.
_REDACT = {"text", "content", "content_json", "text_plain", "body", "password", "token", "excerpt", "question"}


def redact(meta: dict[str, Any] | None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in (meta or {}).items():
        if k in _REDACT:
            out[k] = "[redacted]"
        elif isinstance(v, (int, float, bool)) or v is None:
            out[k] = v
        else:
            out[k] = str(v)[:200]
    return out


def record(
    db: Session,
    action: str,
    *,
    actor_id: uuid.UUID | None,
    project_id: uuid.UUID | None = None,
    object_type: str = "",
    object_id: Any = "",
    actor_type: str = "user",
    meta: dict[str, Any] | None = None,
) -> None:
    db.add(
        AuditEvent(
            actor_id=actor_id,
            actor_type=actor_type,
            project_id=project_id,
            action=action,
            object_type=object_type,
            object_id=str(object_id or ""),
            metadata_redacted=redact(meta),
        )
    )
