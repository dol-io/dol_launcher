from __future__ import annotations

from pathlib import Path

import pytest

import providers
import providers.github as github_module
from core.launcher import Launcher
from core.models import (
    ConflictError,
    NotFoundError,
    RemoteVersion,
    ValidationError,
)
from providers.github import GitHubReleasesProvider


def test_channel_lifecycle_and_cache_invalidation(launcher: Launcher) -> None:
    launcher.add_channel("mirror", repo="owner/repository", asset_regex=r"game.*\.zip")
    cache = launcher.root / ".dolctl" / "cache" / "index" / "mirror.json"
    cache.write_text("{}", encoding="utf-8")

    updated = launcher.update_channel("mirror", repo="other/repository")
    assert updated.repo == "other/repository"
    assert not cache.exists()

    cache.write_text("{}", encoding="utf-8")
    launcher.remove_channel("mirror")
    assert not cache.exists()
    assert "mirror" not in dict(launcher.channels())


def test_channel_conflicts_and_missing_resources(launcher: Launcher) -> None:
    with pytest.raises(ConflictError):
        launcher.add_channel("modloader", preset="dol-modloader")
    with pytest.raises(NotFoundError):
        launcher.update_channel("missing", repo="owner/repository")
    with pytest.raises(NotFoundError):
        launcher.remove_channel("missing")


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({}, "preset or GitHub repository"),
        ({"repo": "not-a-repo"}, "owner/name"),
        ({"repo": "owner/repo", "asset_regex": "["}, "Invalid asset regex"),
        ({"repo": "owner/repo", "provider": "unknown"}, "Unsupported provider"),
        ({"preset": "missing"}, "Unknown channel preset"),
    ],
)
def test_invalid_channel_configuration_is_rejected(
    launcher: Launcher, fields: dict[str, str], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        launcher.add_channel("custom", **fields)


def test_force_replaces_channel(launcher: Launcher) -> None:
    replaced = launcher.add_channel(
        "modloader",
        repo="mirror/modloader",
        asset_regex=r"release\.zip",
        force=True,
    )
    assert replaced.repo == "mirror/modloader"


def test_provider_factory_is_explicit() -> None:
    assert providers.known_providers() == ("github",)
    provider = GitHubReleasesProvider("stable", "owner/repo", r"game.*\.zip")
    assert provider.channel == "stable"


def test_github_provider_filters_and_maps_releases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = [
        {
            "tag_name": "v1.0",
            "name": "Release 1.0",
            "published_at": "2026-01-01T00:00:00Z",
            "html_url": "https://github.invalid/release/1",
            "assets": [
                {
                    "name": "game-v1.0.zip",
                    "browser_download_url": "https://github.invalid/game.zip",
                    "digest": "sha256:" + "a" * 64,
                }
            ],
        },
        {
            "tag_name": "draft",
            "draft": True,
            "assets": [{"name": "game-draft.zip"}],
        },
        {"tag_name": "no-asset", "assets": [{"name": "source.tar.gz"}]},
    ]
    seen: dict[str, object] = {}

    def fake_fetch(url: str, *, headers: dict[str, str]) -> object:
        seen["url"] = url
        seen["headers"] = headers
        return payload

    monkeypatch.setattr(github_module, "fetch_json", fake_fetch)
    versions = GitHubReleasesProvider(
        "stable", "owner/repo", r"game-.*\.zip"
    ).list_versions()
    assert [item.id for item in versions] == ["v1.0"]
    assert versions[0].download_url.endswith("game.zip")
    assert versions[0].sha256 == "a" * 64
    assert (
        seen["url"] == "https://api.github.com/repos/owner/repo/releases?per_page=100"
    )
    assert isinstance(seen["headers"], dict)


def test_github_download_delegates_with_progress(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: dict[str, object] = {}

    def fake_download(url, destination, *, headers, progress, expected_sha256):
        calls.update(
            url=url,
            destination=destination,
            headers=headers,
            progress=progress,
            expected_sha256=expected_sha256,
        )
        return "digest"

    monkeypatch.setattr(github_module, "download_file", fake_download)
    provider = GitHubReleasesProvider("stable", "owner/repo", r".*\.zip")
    version = RemoteVersion(
        id="v1",
        display_name="One",
        channel="stable",
        published_at="",
        asset_name="game.zip",
        download_url="https://example.invalid/game.zip",
        source_ref="",
        sha256="a" * 64,
    )

    def callback(_done: int, _total: int | None) -> None:
        return

    assert (
        provider.download(version, tmp_path / "game.zip", progress=callback) == "digest"
    )
    assert calls["progress"] is callback
    assert calls["url"] == version.download_url
    assert calls["expected_sha256"] == "a" * 64
