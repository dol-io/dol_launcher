"""Channel CRUD: thin helpers around Config.channels writes.

Channels live inside ``.dolctl/config.toml``; this module is the single
write path so the rest of the codebase doesn't reach into Config
directly. Each mutation also clears the matching index cache so the
next ``version remote list`` call refetches.
"""

from __future__ import annotations

from pathlib import Path

import providers
from core.channel_presets import PRESETS, get_preset
from core.models import ChannelConfig, DolCtlError
from core.root import load_config, save_config


def _index_cache_path(root: Path, name: str) -> Path:
    return root / ".dolctl" / "cache" / "index" / f"{name}.json"


def _invalidate_cache(root: Path, name: str) -> None:
    cache = _index_cache_path(root, name)
    if cache.exists():
        cache.unlink()


def list_channels(root: Path) -> list[tuple[str, ChannelConfig]]:
    config = load_config(root)
    return sorted(config.channels.items())


def get_channel(root: Path, name: str) -> ChannelConfig:
    config = load_config(root)
    channel = config.channels.get(name)
    if channel is None:
        raise DolCtlError(f"Channel not configured: {name}")
    return channel


def add_channel(
    root: Path,
    name: str,
    *,
    preset: str | None = None,
    provider: str | None = None,
    repo: str | None = None,
    asset_regex: str | None = None,
    force: bool = False,
) -> ChannelConfig:
    config = load_config(root)
    if name in config.channels and not force:
        raise DolCtlError(
            f"Channel already exists: {name}. Use --force to overwrite."
        )

    if preset is not None:
        try:
            preset_data = get_preset(preset)
        except KeyError:
            known = ", ".join(sorted(PRESETS)) or "(none)"
            raise DolCtlError(
                f"Unknown preset: {preset!r}. Known presets: {known}"
            ) from None
        channel = ChannelConfig(
            provider=provider or preset_data.provider,
            repo=repo or preset_data.repo,
            asset_regex=asset_regex or preset_data.asset_regex,
        )
    else:
        if provider is None or repo is None:
            raise DolCtlError(
                "Either --preset or both --provider and --repo are required."
            )
        channel = ChannelConfig(
            provider=provider,
            repo=repo,
            asset_regex=asset_regex or ChannelConfig().asset_regex,
        )

    if channel.provider not in providers.known_providers():
        raise DolCtlError(
            f"Unknown provider: {channel.provider!r}. "
            f"Known providers: {providers.known_providers()}"
        )

    config.channels[name] = channel
    save_config(root, config)
    _invalidate_cache(root, name)
    return channel


def remove_channel(root: Path, name: str) -> None:
    config = load_config(root)
    if name not in config.channels:
        raise DolCtlError(f"Channel not configured: {name}")
    del config.channels[name]
    save_config(root, config)
    _invalidate_cache(root, name)


def set_channel_fields(
    root: Path,
    name: str,
    *,
    provider: str | None = None,
    repo: str | None = None,
    asset_regex: str | None = None,
) -> ChannelConfig:
    config = load_config(root)
    channel = config.channels.get(name)
    if channel is None:
        raise DolCtlError(f"Channel not configured: {name}")
    if provider is not None:
        if provider not in providers.known_providers():
            raise DolCtlError(
                f"Unknown provider: {provider!r}. "
                f"Known providers: {providers.known_providers()}"
            )
        channel.provider = provider
    if repo is not None:
        channel.repo = repo
    if asset_regex is not None:
        channel.asset_regex = asset_regex
    config.channels[name] = channel
    save_config(root, config)
    _invalidate_cache(root, name)
    return channel
