"""
Mod management module.

Mods are stored as ModLoader-compatible .mod.zip files under mods/<mod_id>/.
Each mod zip must contain a boot.json at the root level (DoL ModLoader format).
"""

from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path
from typing import Optional

from infra.fs import ensure_dir, now_iso
from infra.net import download_file, is_url
from infra.toml import read_toml, write_toml
from core.models import Mod, DolCtlError, mod_from_dict, mod_to_dict


def _mod_dir(root: Path, mod_id: str) -> Path:
    return root / "mods" / mod_id


def _mod_toml_path(root: Path, mod_id: str) -> Path:
    return _mod_dir(root, mod_id) / ".mod.toml"


def _mod_zip_path(root: Path, mod_id: str) -> Path:
    return _mod_dir(root, mod_id) / f"{mod_id}.mod.zip"


def _read_boot_json(zip_path: Path) -> dict | None:
    """Extract and parse boot.json from a mod zip. Returns None if not found."""
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            # Support boot.json at root or inside a single top-level directory
            candidates = [
                n for n in names if n == "boot.json" or n.endswith("/boot.json")
            ]
            if not candidates:
                return None
            # Prefer root-level boot.json
            target = "boot.json" if "boot.json" in candidates else candidates[0]
            data = zf.read(target)
            return json.loads(data.decode("utf-8"))
    except Exception:
        return None


def _slugify_mod_id(name: str) -> str:
    """Convert a display name to a usable mod_id."""
    slug = name.lower().replace(" ", "_")
    slug = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in slug)
    return slug.strip("_") or "mod"


def add_mod_from_zip(
    root: Path,
    path_or_url: str,
    mod_id: Optional[str] = None,
) -> str:
    """
    Import a ModLoader-format .mod.zip into mods/<mod_id>/.

    - If path_or_url is a URL, the zip is downloaded to .dolctl/cache/downloads/ first.
    - boot.json inside the zip is parsed for name/version metadata.
    - Returns the mod_id used.
    """
    source_ref = path_or_url
    source = "local"

    if is_url(path_or_url):
        cache_dir = root / ".dolctl" / "cache" / "downloads"
        ensure_dir(cache_dir)
        filename = path_or_url.rstrip("/").split("/")[-1]
        if not filename.endswith(".zip"):
            filename += ".zip"
        dest_path = cache_dir / filename
        download_file(path_or_url, dest_path)
        zip_path = dest_path
        source = "url"
    else:
        zip_path = Path(path_or_url).expanduser().resolve()
        if not zip_path.exists():
            raise DolCtlError(f"File not found: {zip_path}")

    # Parse boot.json for metadata
    boot = _read_boot_json(zip_path)

    if boot:
        name = boot.get("name") or zip_path.stem
        version = str(boot.get("version") or "")
        author = str(boot.get("author") or "")
        description = str(boot.get("description") or "")
    else:
        name = zip_path.stem.replace(".mod", "")
        version = ""
        author = ""
        description = ""
        # Warn but don't block — user may import non-standard zips
        import warnings

        warnings.warn(
            f"No boot.json found in {zip_path.name}. "
            "This may not be a valid DoL ModLoader mod.",
            stacklevel=2,
        )

    if not mod_id:
        mod_id = _slugify_mod_id(name)

    mod_dir = _mod_dir(root, mod_id)
    if mod_dir.exists():
        raise DolCtlError(
            f"Mod already exists: {mod_id}. Use --id to specify a different id."
        )

    ensure_dir(mod_dir)

    # Copy the zip into the mod directory as <mod_id>.mod.zip
    dest_zip = _mod_zip_path(root, mod_id)
    shutil.copy2(zip_path, dest_zip)

    mod = Mod(
        id=mod_id,
        name=name,
        version=version,
        author=author,
        description=description,
        source=source,
        source_ref=source_ref,
        installed_at=now_iso(),
        path=mod_dir,
    )
    write_toml(_mod_toml_path(root, mod_id), mod_to_dict(mod))
    return mod_id


def get_mod_info(root: Path, mod_id: str) -> Mod:
    """Return Mod metadata for the given mod_id."""
    toml_path = _mod_toml_path(root, mod_id)
    if not toml_path.exists():
        raise DolCtlError(f"Mod not found: {mod_id}")
    data = read_toml(toml_path)
    return mod_from_dict(data, _mod_dir(root, mod_id))


def list_mods(root: Path) -> list[Mod]:
    """Return all installed mods sorted by id."""
    mods_dir = root / "mods"
    if not mods_dir.exists():
        return []
    result: list[Mod] = []
    for entry in sorted(mods_dir.iterdir()):
        if not entry.is_dir():
            continue
        toml_path = entry / ".mod.toml"
        if toml_path.exists():
            data = read_toml(toml_path)
            result.append(mod_from_dict(data, entry))
    return result


def remove_mod(root: Path, mod_id: str) -> None:
    """Delete a mod and its files from mods/<mod_id>/."""
    mod_dir = _mod_dir(root, mod_id)
    if not mod_dir.exists():
        raise DolCtlError(f"Mod not found: {mod_id}")
    shutil.rmtree(mod_dir)
