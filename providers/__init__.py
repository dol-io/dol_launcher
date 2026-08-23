from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from core.models import ChannelConfig, ProgressCallback, RemoteVersion, ValidationError


@runtime_checkable
class VersionProvider(Protocol):
    def list_versions(self) -> list[RemoteVersion]: ...

    def download(
        self,
        version: RemoteVersion,
        destination: Path,
        *,
        progress: ProgressCallback | None = None,
    ) -> str: ...


def known_providers() -> tuple[str, ...]:
    return ("github",)


def create_provider(channel_name: str, config: ChannelConfig) -> VersionProvider:
    if config.provider != "github":
        raise ValidationError(
            f"Unsupported provider {config.provider!r}; available: github"
        )
    from .github import GitHubReleasesProvider

    return GitHubReleasesProvider(channel_name, config.repo, config.asset_regex)


def validate_config(config: ChannelConfig) -> None:
    create_provider("validation", config)
