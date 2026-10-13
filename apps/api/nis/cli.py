"""Operator CLI: `nis migrate | serve | create-admin | demo`."""

import argparse
import getpass
import sys
from pathlib import Path


def _alembic_cfg():
    from alembic.config import Config

    from .config import get_settings

    root = Path(__file__).resolve().parent.parent
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "migrations"))
    cfg.set_main_option("sqlalchemy.url", get_settings().database_url)
    return cfg


def migrate() -> None:
    from alembic import command

    command.upgrade(_alembic_cfg(), "head")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="nis", description="Novel Intelligence Studio operator CLI")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrate", help="apply database migrations")
    sv = sub.add_parser("serve", help="run the API (and the built control panel)")
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=8000)
    ca = sub.add_parser("create-admin", help="create or promote an administrator")
    ca.add_argument("email")
    sub.add_parser("demo", help="load a small original Arabic demo project (no copyrighted text)")
    a = p.parse_args(argv)

    if a.cmd == "migrate":
        migrate()
        print("migrations applied")
    elif a.cmd == "serve":
        import uvicorn

        migrate()
        uvicorn.run("nis.main:app", host=a.host, port=a.port, proxy_headers=True)
    elif a.cmd == "create-admin":
        from sqlalchemy import select

        from .db import SessionLocal
        from .models import User
        from .security import hash_password

        migrate()
        db = SessionLocal()
        u = db.scalar(select(User).where(User.email == a.email.lower()))
        if u is None:
            pw = getpass.getpass("password (≥10 chars): ")
            if len(pw) < 10:
                print("password too short", file=sys.stderr)
                return 2
            u = User(email=a.email.lower(), display_name=a.email.split("@")[0], password_hash=hash_password(pw))
            db.add(u)
        u.is_admin = True
        db.commit()
        print(f"admin ready: {u.email}")
    elif a.cmd == "demo":
        from .demo import load_demo

        migrate()
        print(load_demo())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
