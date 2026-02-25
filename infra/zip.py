from __future__ import annotations

from pathlib import Path
import shutil
import zipfile


def extract_zip(src: Path, dest: Path, strip_single_dir: bool = False) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(src, "r") as zip_handle:
        zip_handle.extractall(dest)
    if strip_single_dir:
        entries = list(dest.iterdir())
        if len(entries) == 1 and entries[0].is_dir():
            inner = entries[0]
            for item in inner.iterdir():
                shutil.move(str(item), dest / item.name)
            shutil.rmtree(inner)
