"""SHA-256 hashing utilities (Section 12.4).

Every artifact must carry a SHA-256 hash. These helpers are the single source
of truth for how that hash is computed so the value is reproducible.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

_CHUNK = 1024 * 1024


def hash_bytes(data: bytes) -> str:
    """Return the SHA-256 hex digest of ``data``."""
    return hashlib.sha256(data).hexdigest()


def hash_text(text: str) -> str:
    """Return the SHA-256 hex digest of ``text`` (UTF-8)."""
    return hash_bytes(text.encode("utf-8"))


def hash_file(path: str | Path) -> str:
    """Return the SHA-256 hex digest of a file's contents, streamed."""
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()
