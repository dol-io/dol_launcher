from __future__ import annotations

import io
import json
from pathlib import Path
import shutil
import tarfile
import zipfile

import pytest

import core.imagepacks as imagepacks_module
from core.launcher import Launcher
from core.models import NotFoundError
import providers.gitlab as gitlab_module
from providers.gitlab import GitLabCommit, GitLabRepositoryProvider


def _source_archive(path: Path) -> Path:
    with tarfile.open(path, "w:gz") as archive:
        image = b"png fixture"
        image_info = tarfile.TarInfo(
            "repository-a1b2c3d4/imagepacks/mysterious/sex/scene/frame.png"
        )
        image_info.size = len(image)
        archive.addfile(image_info, io.BytesIO(image))
        note = b"not an image"
        note_info = tarfile.TarInfo(
            "repository-a1b2c3d4/imagepacks/mysterious/README.txt"
        )
        note_info.size = len(note)
        archive.addfile(note_info, io.BytesIO(note))
    return path


def test_imagepack_catalog_is_separate_from_release_channels(
    launcher: Launcher,
) -> None:
    recipes = launcher.imagepacks()
    assert [recipe.id for recipe in recipes] == ["dolp-mysterious-ucb"]
    assert recipes[0].path == "imagepacks/mysterious"
    assert "dolp-mysterious-ucb" not in dict(launcher.channel_presets())


def test_gitlab_provider_resolves_latest_path_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}

    def fake_fetch(url: str, *, headers: dict[str, str]) -> object:
        seen["url"] = url
        seen["headers"] = headers
        return [
            {
                "id": "a1b2c3d4" * 5,
                "short_id": "a1b2c3d4",
                "committed_date": "2026-08-09T00:00:00Z",
                "title": "Update mysterious images",
                "web_url": "https://gitgud.invalid/project/-/commit/a1b2c3d4",
            }
        ]

    monkeypatch.setattr(gitlab_module, "fetch_json", fake_fetch)
    provider = GitLabRepositoryProvider(
        "https://gitgud.invalid",
        28315,
        "https://gitgud.invalid/project",
    )
    commit = provider.latest_commit("master", "imagepacks/mysterious")

    assert commit.short_id == "a1b2c3d4"
    assert commit.title == "Update mysterious images"
    assert "ref_name=master" in str(seen["url"])
    assert "path=imagepacks%2Fmysterious" in str(seen["url"])


def test_gitlab_provider_download_is_pinned_to_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}

    def fake_download(url, destination, *, headers, progress):
        seen.update(
            url=url,
            destination=destination,
            headers=headers,
            progress=progress,
        )
        return "digest"

    monkeypatch.setattr(gitlab_module, "download_file", fake_download)
    provider = GitLabRepositoryProvider(
        "https://gitgud.invalid",
        28315,
        "https://gitgud.invalid/project",
    )
    commit = GitLabCommit(
        id="a1b2c3d4" * 5,
        short_id="a1b2c3d4",
        committed_date="",
        title="",
        web_url="https://gitgud.invalid/project/-/commit/a1b2c3d4",
    )
    def callback(_done: int, _total: int | None) -> None:
        return

    destination = tmp_path / "source.tar.gz"

    assert (
        provider.download_archive(
            commit,
            "imagepacks/mysterious",
            destination,
            progress=callback,
        )
        == "digest"
    )
    assert f"sha={commit.id}" in str(seen["url"])
    assert "path=imagepacks%2Fmysterious" in str(seen["url"])
    assert seen["destination"] == destination
    assert seen["progress"] is callback


def test_install_imagepack_generates_an_imageloader_mod(
    launcher: Launcher,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _source_archive(tmp_path / "source.tar.gz")
    commit = GitLabCommit(
        id="a1b2c3d4" * 5,
        short_id="a1b2c3d4",
        committed_date="2026-08-09T00:00:00Z",
        title="Update mysterious images",
        web_url="https://gitgud.invalid/project/-/commit/a1b2c3d4",
    )
    downloads: list[tuple[GitLabCommit, str, Path]] = []

    class FakeProvider:
        def latest_commit(self, ref: str, path: str) -> GitLabCommit:
            assert ref == "master"
            assert path == "imagepacks/mysterious"
            return commit

        def download_archive(
            self,
            selected: GitLabCommit,
            path: str,
            destination: Path,
            *,
            progress=None,
        ) -> str:
            downloads.append((selected, path, destination))
            shutil.copy2(source, destination)
            if progress is not None:
                progress(source.stat().st_size, source.stat().st_size)
            return "digest"

    monkeypatch.setattr(
        imagepacks_module,
        "GitLabRepositoryProvider",
        lambda *_args: FakeProvider(),
    )
    ticks: list[tuple[int, int | None]] = []
    installed = launcher.install_imagepack(
        "dolp-mysterious-ucb",
        progress=lambda done, total: ticks.append((done, total)),
    )

    assert installed == "dolp-mysterious-ucb"
    mod = launcher.mod(installed)
    assert mod.source == "imagepack"
    assert mod.source_ref == commit.web_url
    assert mod.version == "0.0.0+a1b2c3d4"
    assert downloads[0][0] is commit
    assert downloads[0][1] == "imagepacks/mysterious"
    assert commit.short_id in downloads[0][2].name
    assert ticks

    archive_path = mod.path / f"{installed}.mod.zip"
    with zipfile.ZipFile(archive_path) as archive:
        boot = json.loads(archive.read("boot.json"))
        assert boot["imgFileList"] == ["img/sex/scene/frame.png"]
        assert boot["addonPlugin"][0]["addonName"] == "ImageLoaderAddon"
        assert archive.read("img/sex/scene/frame.png") == b"png fixture"
        assert "img/README.txt" not in archive.namelist()


def test_unknown_imagepack_recipe_is_rejected(launcher: Launcher) -> None:
    with pytest.raises(NotFoundError, match="not found"):
        launcher.install_imagepack("missing")
