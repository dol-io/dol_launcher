from __future__ import annotations

from pathlib import Path

import providers

from .channel_presets import PRESETS, get_preset
from .models import (
    ChannelConfig,
    ChannelKind,
    ConflictError,
    NotFoundError,
    ValidationError,
)
from .root import RootLayout, load_config, save_config, validate_resource_name


def list_channels(root: Path) -> list[tuple[str, ChannelConfig]]:
    return sorted(load_config(root).channels.items())


def get_channel(root: Path, name: str) -> ChannelConfig:
    name = validate_resource_name(name, "channel")
    channel = load_config(root).channels.get(name)
    if channel is None:
        raise NotFoundError(f"Channel not found: {name}")
    return channel


def _invalidate_cache(root: Path, name: str) -> None:
    cache_file = RootLayout.open(root).channel_cache_file(name)
    cache_file.unlink(missing_ok=True)


def _channel_from_input(
    *,
    preset: str | None,
    kind: ChannelKind | None,
    provider: str | None,
    repo: str | None,
    asset_regex: str | None,
) -> ChannelConfig:
    if preset is not None:
        try:
            template = get_preset(preset)
        except KeyError as exc:
            known = ", ".join(sorted(PRESETS))
            raise ValidationError(
                f"Unknown channel preset {preset!r}; available: {known}"
            ) from exc
        channel = ChannelConfig(
            kind=kind or template.kind,
            provider=provider or template.provider,
            repo=repo or template.repo,
            asset_regex=asset_regex or template.asset_regex,
        )
    else:
        if not repo:
            raise ValidationError("A preset or GitHub repository is required")
        channel = ChannelConfig(
            kind=kind or "game",
            provider=provider or "github",
            repo=repo,
            asset_regex=asset_regex or ChannelConfig().asset_regex,
        )
    providers.validate_config(channel)
    return channel


def add_channel(
    root: Path,
    name: str,
    *,
    preset: str | None = None,
    kind: ChannelKind | None = None,
    provider: str | None = None,
    repo: str | None = None,
    asset_regex: str | None = None,
    force: bool = False,
) -> ChannelConfig:
    name = validate_resource_name(name, "channel")
    config = load_config(root)
    if name in config.channels and not force:
        raise ConflictError(f"Channel already exists: {name}")
    channel = _channel_from_input(
        preset=preset,
        kind=kind,
        provider=provider,
        repo=repo,
        asset_regex=asset_regex,
    )
    config.channels[name] = channel
    save_config(root, config)
    _invalidate_cache(root, name)
    return channel


def update_channel(
    root: Path,
    name: str,
    *,
    kind: ChannelKind | None = None,
    provider: str | None = None,
    repo: str | None = None,
    asset_regex: str | None = None,
) -> ChannelConfig:
    name = validate_resource_name(name, "channel")
    config = load_config(root)
    current = config.channels.get(name)
    if current is None:
        raise NotFoundError(f"Channel not found: {name}")
    updated = ChannelConfig(
        kind=kind if kind is not None else current.kind,
        provider=provider if provider is not None else current.provider,
        repo=repo if repo is not None else current.repo,
        asset_regex=(asset_regex if asset_regex is not None else current.asset_regex),
        extra=dict(current.extra),
    )
    providers.validate_config(updated)
    config.channels[name] = updated
    save_config(root, config)
    _invalidate_cache(root, name)
    return updated


def set_channel_fields(
    root: Path,
    name: str,
    *,
    kind: ChannelKind | None = None,
    provider: str | None = None,
    repo: str | None = None,
    asset_regex: str | None = None,
) -> ChannelConfig:
    return update_channel(
        root,
        name,
        kind=kind,
        provider=provider,
        repo=repo,
        asset_regex=asset_regex,
    )


def remove_channel(root: Path, name: str) -> None:
    name = validate_resource_name(name, "channel")
    config = load_config(root)
    if name not in config.channels:
        raise NotFoundError(f"Channel not found: {name}")
    del config.channels[name]
    save_config(root, config)
    _invalidate_cache(root, name)
