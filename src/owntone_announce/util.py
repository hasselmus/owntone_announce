from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def validate_name(name: str) -> str:
    if not NAME_RE.fullmatch(name):
        raise ValueError(
            "Announcement name must match [a-z0-9][a-z0-9_-]{0,63}"
        )
    return name


def default_label(name: str) -> str:
    return name.replace("-", " ").replace("_", " ").title()


def atomic_write_json(path: Path, data: Any, *, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    st = path.stat() if path.exists() else None
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, st.st_mode & 0o777 if st else mode)
        if st is not None and hasattr(os, "chown"):
            try:
                os.chown(tmp, st.st_uid, st.st_gid)
            except PermissionError:
                pass
        os.replace(tmp, path)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
