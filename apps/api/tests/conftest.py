import os
import tempfile
import uuid
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="nis-test-"))
os.environ.setdefault("NIS_DATABASE_URL", f"sqlite:///{_TMP / 'test.db'}")
os.environ["NIS_DATA_DIR"] = str(_TMP / "data")
os.environ["NIS_RUNS_INLINE"] = "true"
os.environ["NIS_RATE_LIMIT_PER_MINUTE"] = "0"
os.environ["NIS_AUTH_RATE_LIMIT_PER_MINUTE"] = "0"
os.environ["NIS_LLM_PROVIDER"] = "disabled"
os.environ["NIS_SERVE_SPA"] = "false"

from fastapi.testclient import TestClient  # noqa: E402

from nis.cli import migrate  # noqa: E402
from nis.config import get_settings  # noqa: E402
from nis.db import reset_engine  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _db():
    get_settings.cache_clear()
    reset_engine()
    if get_settings().database_url.startswith("postgresql"):
        from sqlalchemy import text

        from nis.db import get_engine

        with get_engine().begin() as c:
            c.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    migrate()
    yield


@pytest.fixture(scope="session")
def client():
    from nis.main import create_app

    with TestClient(create_app()) as c:
        yield c


class Writer:
    """A registered user with helpers that exercise the real HTTP API."""

    def __init__(self, client: TestClient, name: str):
        self.c = client
        self.email = f"{name}-{uuid.uuid4().hex[:8]}@example.test"
        r = client.post("/v1/auth/register", json={"email": self.email, "password": "correct-horse-1",
                                                   "display_name": name})
        assert r.status_code == 201, r.text
        self.token = r.json()["token"]
        self.user = r.json()["user"]
        self.h = {"Authorization": f"Bearer {self.token}"}

    def get(self, url, **kw):
        return self.c.get(url, headers={**self.h, **kw.pop("headers", {})}, **kw)

    def post(self, url, **kw):
        return self.c.post(url, headers={**self.h, **kw.pop("headers", {})}, **kw)

    def put(self, url, **kw):
        return self.c.put(url, headers={**self.h, **kw.pop("headers", {})}, **kw)

    def patch(self, url, **kw):
        return self.c.patch(url, headers={**self.h, **kw.pop("headers", {})}, **kw)

    def delete(self, url, **kw):
        return self.c.request("DELETE", url, headers={**self.h, **kw.pop("headers", {})}, **kw)

    # domain helpers
    def project(self, title="رواية الاختبار", **kw):
        r = self.post("/v1/projects", json={"title": title, **kw})
        assert r.status_code == 201, r.text
        return r.json()

    def node(self, pid, type_, title="", parent=None, meta=None):
        r = self.post(f"/v1/projects/{pid}/nodes", json={"type": type_, "title": title, "parent_id": parent,
                                                          "meta": meta or {}})
        assert r.status_code == 201, r.text
        return r.json()

    def write(self, doc_id, text, kind="checkpoint", version=None, save_id=None):
        from nis.text import doc_from_plain

        if version is None:
            version = self.get(f"/v1/documents/{doc_id}").json()["version"]
        r = self.put(f"/v1/documents/{doc_id}", headers={"If-Match": f'W/"{version}"'},
                     json={"content_json": doc_from_plain(text), "kind": kind, "client_save_id": save_id})
        return r

    def run(self, pid, agent, skills=None, key=None, **kw):
        r = self.post("/v1/agents/runs", json={"project_id": pid, "agent_id": agent, "skills": skills,
                                               "idempotency_key": key or uuid.uuid4().hex, **kw})
        return r


@pytest.fixture
def writer(client):
    return Writer(client, "writer")


@pytest.fixture
def other(client):
    return Writer(client, "intruder")


@pytest.fixture
def make_writer(client):
    return lambda name="w": Writer(client, name)
