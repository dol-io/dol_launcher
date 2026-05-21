from __future__ import annotations

from pathlib import Path

import pytest

import providers
from core.models import (
    ChannelConfig,
    Config,
    DolCtlError,
    RemoteVersion,
    config_from_dict,
    config_to_dict,
)


class TestRegistry:
    def test_github_is_pre_registered(self) -> None:
        assert "github" in providers.known_providers()

    def test_get_provider_resolves_github(self) -> None:
        cfg = ChannelConfig(provider="github", repo="x/y", asset_regex=r".*\.zip$")
        provider = providers.get_provider("vanilla", cfg)
        from providers.github import GitHubReleasesProvider

        assert isinstance(provider, GitHubReleasesProvider)

    def test_get_provider_unknown_raises(self) -> None:
        cfg = ChannelConfig(provider="not-a-real-provider", repo="x/y")
        with pytest.raises(DolCtlError):
            providers.get_provider("ghost", cfg)

    def test_register_decorator_adds_factory(self) -> None:
        @providers.register("test-only-temp")
        def _factory(name: str, cfg: ChannelConfig):
            return _FakeProvider(name)

        try:
            cfg = ChannelConfig(provider="test-only-temp")
            instance = providers.get_provider("alpha", cfg)
            assert isinstance(instance, _FakeProvider)
            assert instance.name == "alpha"
        finally:
            providers.REGISTRY.pop("test-only-temp", None)

    def test_double_register_raises(self) -> None:
        @providers.register("test-only-dup")
        def _f1(name: str, cfg: ChannelConfig):
            return _FakeProvider(name)

        try:
            with pytest.raises(ValueError):

                @providers.register("test-only-dup")
                def _f2(name: str, cfg: ChannelConfig):
                    return _FakeProvider(name)
        finally:
            providers.REGISTRY.pop("test-only-dup", None)


class _FakeProvider:
    """Minimal provider used only in tests; satisfies the Protocol."""

    def __init__(self, name: str) -> None:
        self.name = name

    def list_versions(self) -> list[RemoteVersion]:
        return []

    def download(self, version: RemoteVersion, dest: Path) -> str:
        return "deadbeef"


class TestChannelConfigExtra:
    def test_round_trip_preserves_extra(self) -> None:
        cfg = Config(
            channels={
                "weird": ChannelConfig(
                    provider="custom",
                    repo="",
                    asset_regex=r".*",
                    extra={"manifest_url": "https://example.com/manifest.json"},
                )
            }
        )
        data = config_to_dict(cfg)
        round_tripped = config_from_dict(data)
        assert round_tripped.channels["weird"].extra == {
            "manifest_url": "https://example.com/manifest.json"
        }

    def test_extra_excludes_reserved_keys(self) -> None:
        # `provider`/`repo`/`asset_regex` must never leak into `extra`
        data = {
            "channels": {
                "vanilla": {
                    "provider": "github",
                    "repo": "x/y",
                    "asset_regex": r".*\.zip$",
                    "custom": "yes",
                }
            }
        }
        cfg = config_from_dict(data)
        assert cfg.channels["vanilla"].extra == {"custom": "yes"}
        assert "provider" not in cfg.channels["vanilla"].extra
