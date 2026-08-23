from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import shutil
import zipfile

from infra.fs import staging_directory
from infra.tar import extract_tar
from providers.gitlab import GitLabCommit, GitLabRepositoryProvider

from .models import (
    DolCtlError,
    ExternalError,
    NotFoundError,
    ProgressCallback,
    ValidationError,
)
from .mods import publish_mod_archive
from .root import RootLayout


_IMAGE_EXTENSIONS = {".avif", ".gif", ".jpeg", ".jpg", ".png", ".svg", ".webp"}
_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


@dataclass(frozen=True, slots=True)
class ImagepackRecipe:
    id: str
    name: str
    description: str
    author: str
    source_label: str
    base_url: str
    project_id: int
    project_url: str
    ref: str
    path: str


_RECIPES: dict[str, ImagepackRecipe] = {
    "dolp-mysterious-ucb": ImagepackRecipe(
        id="dolp-mysterious-ucb",
        name="DOLP Mysterious / UCB Imagepack",
        description=(
            "DOLP-maintained Mysterious/UCB combat images, packaged locally "
            "for ModLoader."
        ),
        author="Mysterious/UCB contributors and DOLP maintainers",
        source_label="DOLP on GitGud",
        base_url="https://gitgud.io",
        project_id=28315,
        project_url="https://gitgud.io/Frostberg/degrees-of-lewdity-plus",
        ref="master",
        path="imagepacks/mysterious",
    ),
}


def list_imagepacks() -> list[ImagepackRecipe]:
    return [_RECIPES[key] for key in sorted(_RECIPES)]


def get_imagepack(recipe_id: str) -> ImagepackRecipe:
    try:
        return _RECIPES[recipe_id]
    except KeyError as exc:
        raise NotFoundError(f"Imagepack recipe not found: {recipe_id}") from exc


def _image_files(source: Path) -> list[Path]:
    files = sorted(
        path
        for path in source.rglob("*")
        if path.is_file()
        and not path.is_symlink()
        and path.suffix.lower() in _IMAGE_EXTENSIONS
    )
    if not files:
        raise ValidationError("Imagepack source contains no supported images")
    return files


def _write_file(archive: zipfile.ZipFile, source: Path, member_name: str) -> None:
    info = zipfile.ZipInfo(member_name, date_time=_ZIP_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    info.file_size = source.stat().st_size
    with source.open("rb") as source_handle, archive.open(info, "w") as target_handle:
        shutil.copyfileobj(source_handle, target_handle)


def _build_mod_archive(
    source: Path,
    destination: Path,
    recipe: ImagepackRecipe,
    commit: GitLabCommit,
) -> None:
    images = _image_files(source)
    image_members = [f"img/{path.relative_to(source).as_posix()}" for path in images]
    boot = {
        "name": recipe.name,
        "version": f"0.0.0+{commit.short_id}",
        "author": recipe.author,
        "description": recipe.description,
        "styleFileList": [],
        "scriptFileList": [],
        "tweeFileList": [],
        "additionFile": [],
        "imgFileList": image_members,
        "addonPlugin": [
            {
                "modName": "ModLoader DoL ImageLoaderHook",
                "addonName": "ImageLoaderAddon",
                "modVersion": "^2.3.0",
                "params": [],
            }
        ],
        "dependenceInfo": [
            {
                "modName": "ModLoader DoL ImageLoaderHook",
                "version": "^2.3.0",
            }
        ],
    }
    with zipfile.ZipFile(
        destination, "w", compression=zipfile.ZIP_DEFLATED
    ) as archive:
        archive.writestr(
            zipfile.ZipInfo("boot.json", date_time=_ZIP_TIMESTAMP),
            json.dumps(boot, ensure_ascii=False, indent=2).encode("utf-8"),
            compress_type=zipfile.ZIP_DEFLATED,
        )
        for source_file, member_name in zip(images, image_members, strict=True):
            _write_file(archive, source_file, member_name)


def install_imagepack(
    root: Path,
    recipe_id: str,
    mod_id: str | None = None,
    *,
    force: bool = False,
    progress: ProgressCallback | None = None,
) -> str:
    """Pin, download, package, and publish a reviewed imagepack as a Mod."""
    layout = RootLayout.open(root)
    recipe = get_imagepack(recipe_id)
    provider = GitLabRepositoryProvider(
        recipe.base_url,
        recipe.project_id,
        recipe.project_url,
    )
    try:
        commit = provider.latest_commit(recipe.ref, recipe.path)
        cached_archive = (
            layout.download_cache
            / f"imagepack-{recipe.id}-{commit.short_id}.tar.gz"
        )
        provider.download_archive(
            commit,
            recipe.path,
            cached_archive,
            progress=progress,
        )
        with staging_directory(layout.root, "imagepacks") as workspace:
            extracted = workspace / "source"
            extract_tar(cached_archive, extracted, strip_single_dir=True)
            image_root = extracted.joinpath(*recipe.path.split("/"))
            if not image_root.is_dir() or image_root.is_symlink():
                raise ValidationError(
                    f"Downloaded archive does not contain {recipe.path}"
                )
            generated = workspace / f"{recipe.id}.mod.zip"
            _build_mod_archive(image_root, generated, recipe, commit)
            return publish_mod_archive(
                layout,
                generated,
                mod_id or recipe.id,
                source_kind="imagepack",
                source_ref=commit.web_url,
                force=force,
            )
    except DolCtlError:
        raise
    except Exception as exc:
        raise ExternalError(
            f"Could not install imagepack {recipe.id}: {exc}"
        ) from exc
