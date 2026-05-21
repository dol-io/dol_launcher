from __future__ import annotations

from pathlib import Path

import pytest

from core.channel_presets import PRESETS
from core.channels import (
    add_channel,
    get_channel,
    list_channels,
    remove_channel,
    set_channel_fields,
)
from core.models import DolCtlError
from core.root import load_config


class TestAddChannel:
    def test_with_preset(self, root: Path) -> None:
        cfg = add_channel(root, "vanilla", preset="dol-vanilla")
        preset = PRESETS["dol-vanilla"]
        assert cfg.provider == preset.provider
        assert cfg.repo == preset.repo
        assert cfg.asset_regex == preset.asset_regex
        # Persisted to config.toml
        assert load_config(root).channels["vanilla"].repo == preset.repo

    def test_without_preset_requires_provider_and_repo(self, root: Path) -> None:
        with pytest.raises(DolCtlError):
            add_channel(root, "vanilla")
        with pytest.raises(DolCtlError):
            add_channel(root, "vanilla", provider="github")

    def test_explicit_fields_override_preset(self, root: Path) -> None:
        cfg = add_channel(
            root,
            "vanilla-mirror",
            preset="dol-vanilla",
            repo="mirror/dol",
        )
        assert cfg.repo == "mirror/dol"
        # Provider and regex still come from the preset
        assert cfg.provider == PRESETS["dol-vanilla"].provider

    def test_unknown_preset_rejected(self, root: Path) -> None:
        with pytest.raises(DolCtlError):
            add_channel(root, "x", preset="nonexistent")

    def test_unknown_provider_rejected(self, root: Path) -> None:
        with pytest.raises(DolCtlError):
            add_channel(root, "x", provider="not-a-thing", repo="a/b")

    def test_duplicate_rejected_without_force(self, root: Path) -> None:
        add_channel(root, "vanilla", preset="dol-vanilla")
        with pytest.raises(DolCtlError):
            add_channel(root, "vanilla", preset="dol-vanilla")

    def test_force_overwrites(self, root: Path) -> None:
        add_channel(root, "vanilla", preset="dol-vanilla")
        cfg = add_channel(
            root,
            "vanilla",
            preset="dol-vanilla",
            repo="mirror/x",
            force=True,
        )
        assert cfg.repo == "mirror/x"


class TestSetAndRemoveChannel:
    def test_set_individual_fields(self, root: Path) -> None:
        add_channel(root, "vanilla", preset="dol-vanilla")
        set_channel_fields(root, "vanilla", repo="someone/else")
        assert get_channel(root, "vanilla").repo == "someone/else"
        # other fields preserved
        assert get_channel(root, "vanilla").asset_regex == PRESETS["dol-vanilla"].asset_regex

    def test_set_unknown_channel_raises(self, root: Path) -> None:
        with pytest.raises(DolCtlError):
            set_channel_fields(root, "ghost", repo="a/b")

    def test_set_unknown_provider_raises(self, root: Path) -> None:
        add_channel(root, "vanilla", preset="dol-vanilla")
        with pytest.raises(DolCtlError):
            set_channel_fields(root, "vanilla", provider="not-a-thing")

    def test_remove_channel(self, root: Path) -> None:
        add_channel(root, "vanilla", preset="dol-vanilla")
        remove_channel(root, "vanilla")
        assert list_channels(root) == []

    def test_remove_unknown_channel_raises(self, root: Path) -> None:
        with pytest.raises(DolCtlError):
            remove_channel(root, "ghost")


class TestCacheInvalidation:
    def test_remove_clears_index_cache(self, root: Path) -> None:
        add_channel(root, "vanilla", preset="dol-vanilla")
        cache_path = root / ".dolctl" / "cache" / "index" / "vanilla.json"
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text("{}", encoding="utf-8")
        remove_channel(root, "vanilla")
        assert not cache_path.exists()
