from __future__ import annotations

from pathlib import Path
import tomllib
import tomli_w


def read_toml(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("rb") as handle:
        return tomllib.load(handle)


def write_toml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = tomli_w.dumps(data)
    if not content.endswith("\n"):
        content += "\n"
    path.write_text(content, encoding="utf-8")
