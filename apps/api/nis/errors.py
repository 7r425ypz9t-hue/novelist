"""RFC 9457 Problem Details for every error response."""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

PROBLEM_JSON = "application/problem+json"


class ProblemError(Exception):
    def __init__(self, status: int, title: str, detail: str = "", type_: str = "about:blank", **extra: Any):
        self.status = status
        self.title = title
        self.detail = detail
        self.type = type_
        self.extra = extra


def not_found(what: str = "المورد") -> ProblemError:
    # 404 for both "missing" and "not yours": never reveal existence across projects (AT12).
    return ProblemError(404, "غير موجود", f"{what} غير موجود أو لا تملك صلاحية الوصول إليه.", "/problems/not-found")


def forbidden(detail: str) -> ProblemError:
    return ProblemError(403, "غير مسموح", detail, "/problems/forbidden")


def conflict(detail: str, **extra: Any) -> ProblemError:
    return ProblemError(409, "تعارض", detail, "/problems/conflict", **extra)


def bad_request(detail: str, **extra: Any) -> ProblemError:
    return ProblemError(400, "طلب غير صالح", detail, "/problems/bad-request", **extra)


def _problem(request: Request, status: int, title: str, detail: str, type_: str, **extra: Any) -> JSONResponse:
    body = {"type": type_, "title": title, "status": status, "detail": detail, "instance": request.url.path}
    body.update(extra)
    return JSONResponse(body, status_code=status, media_type=PROBLEM_JSON)


def install(app: FastAPI) -> None:
    @app.exception_handler(ProblemError)
    async def _problem_handler(request: Request, exc: ProblemError):
        return _problem(request, exc.status, exc.title, exc.detail, exc.type, **exc.extra)

    @app.exception_handler(StarletteHTTPException)
    async def _http_handler(request: Request, exc: StarletteHTTPException):
        title = {401: "غير مصادق", 404: "غير موجود", 405: "طريقة غير مسموحة", 429: "طلبات كثيرة"}.get(
            exc.status_code, "خطأ"
        )
        return _problem(request, exc.status_code, title, str(exc.detail), "about:blank")

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(request: Request, exc: RequestValidationError):
        errors = [{"loc": list(e.get("loc", [])), "msg": e.get("msg", "")} for e in exc.errors()]
        return _problem(request, 422, "بيانات غير صالحة", "تحقق من الحقول المرسلة.", "/problems/validation",
                        errors=errors)
