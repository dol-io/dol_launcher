from __future__ import annotations

from pathlib import Path
import re

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


def test_built_in_presets_cover_common_game_and_mod_releases() -> None:
    presets = dict(Launcher.channel_presets())
    assert set(presets) == {
        "au-female-model-058",
        "ausdol-facial-expansion",
        "cheat-lyra",
        "combat-status-display-lyra",
        "dol-i18n-zh",
        "dol-image-pack",
        "dol-modloader",
        "dol-modloader-zh",
        "doli",
        "ucb",
    }
    assert presets["dol-modloader"].kind == "game"
    assert presets["dol-modloader-zh"].kind == "game"
    assert presets["dol-image-pack"].kind == "mod"
    assert presets["dol-i18n-zh"].kind == "mod"
    assert presets["doli"].kind == "mod"
    assert presets["cheat-lyra"].kind == "mod"
    assert presets["combat-status-display-lyra"].kind == "mod"
    assert presets["au-female-model-058"].kind == "mod"
    assert presets["ausdol-facial-expansion"].kind == "mod"
    assert presets["ucb"].kind == "mod"

    known_assets = {
        "au-female-model-058": "AUfemale.model_v0.8.7.zip",
        "ausdol-facial-expansion": "AUsDoL.facial.expansion.mod.zip",
        "cheat-lyra": "Cheat-Lyra-v1.1.3.mod.zip",
        "combat-status-display-lyra": (
            "CombatStatusDisplay-Lyra-v1.0.1.mod.zip"
        ),
        "dol-modloader": "DoL-ModLoader-2.101.1-dol-0.5.11.9-deadbeef.zip",
        "dol-modloader-zh": "DoL-ModLoader-0.5.11.9-v2.101.1.zip",
        "dol-image-pack": "GameOriginalImagePack.mod.zip",
        "dol-i18n-zh": "ModI18N-0.5.11.9-chs-1.0.0a.mod.zip",
        "doli": "DOLI.mod.zip",
        "ucb": "default.zip",
    }
    for key, asset in known_assets.items():
        assert re.fullmatch(presets[key].asset_regex, asset)
    assert not re.fullmatch(
        presets["dol-modloader-zh"].asset_regex,
        "DoL-ModLoader-0.5.11.9-v2.101.1-polyfill.zip",
    )
    assert not re.fullmatch(
        presets["au-female-model-058"].asset_regex,
        "AUfemale.model_v0.9.3.zip",
    )


def test_mod_preset_materialises_a_typed_channel(launcher: Launcher) -> None:
    channel = launcher.add_channel("image-pack", preset="dol-image-pack")
    assert channel.kind == "mod"
    assert dict(launcher.channels())["image-pack"].kind == "mod"


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
        ({"repo": "owner/repo", "kind": "other"}, "kind must be"),
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
