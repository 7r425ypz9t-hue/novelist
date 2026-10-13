"""Object storage abstraction. Local filesystem implementation; an S3-compatible backend can implement
the same three methods without touching domain code."""

import shutil
from pathlib import Path

from .config import get_settings


class LocalObjectStore:
    def __init__(self, root: Path | None = None):
        self.root = (root or get_settings().data_dir / "objects").resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if self.root not in p.parents:
            raise ValueError("invalid object key")
        return p

    def put(self, key: str, data: bytes) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(p)

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        p = self._path(key)
        if p.exists():
            p.unlink()

    def delete_prefix(self, prefix: str) -> None:
        p = self._path(prefix)
        if p.is_dir():
            shutil.rmtree(p)

    def writable(self) -> bool:
        try:
            self.put(".healthcheck", b"ok")
            self.delete(".healthcheck")
            return True
        except OSError:
            return False


def store() -> LocalObjectStore:
    return LocalObjectStore()
