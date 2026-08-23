from __future__ import annotations

from pathlib import Path
import tomllib

import tomli_w

from .fs import atomic_write_text


def read_toml(path: Path) -> dict:
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    if not isinstance(data, dict):
        raise tomllib.TOMLDecodeError("Top-level TOML value must be a table")
    return data


def write_toml(path: Path, data: dict) -> None:
    content = tomli_w.dumps(data)
    if not content.endswith("\n"):
        content += "\n"
    atomic_write_text(path, content)
