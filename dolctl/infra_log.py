from __future__ import annotations

from pathlib import Path
import traceback
from datetime import datetime, timezone

from .infra_fs import ensure_dir


def log_error(root: Path, message: str, exc: Exception | None = None) -> None:
    log_dir = root / ".dolctl" / "logs"
    ensure_dir(log_dir)
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    log_path = log_dir / f"{datetime.now(timezone.utc).date().isoformat()}.log"
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(f"[{timestamp}] {message}\n")
        if exc is not None:
            handle.write("".join(traceback.format_exception(exc)))
            handle.write("\n")
