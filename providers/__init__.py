"""Version provider registry.

A *version provider* maps a logical channel (vanilla, variant_plus, …) to
the remote that actually hosts release artefacts. Providers are pluggable:
each implementation registers a factory under a stable name (see the
``register`` decorator), and :func:`get_provider` looks the factory up by
the ``provider`` field on a :class:`core.models.ChannelConfig`.

To add a new provider, drop a module under ``providers/`` that imports
``register`` and decorates either the provider class itself (when its
``__init__`` matches ``(channel_name, ChannelConfig)``) or a factory
function returning a provider instance.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Protocol, runtime_checkable

from core.models import ChannelConfig, RemoteVersion


@runtime_checkable
class VersionProvider(Protocol):
    """Minimum interface every channel provider exposes."""

    def list_versions(self) -> list[RemoteVersion]:
        ...

    def download(self, version: RemoteVersion, dest: Path) -> str:
        ...


ProviderFactory = Callable[[str, ChannelConfig], VersionProvider]

REGISTRY: dict[str, ProviderFactory] = {}


def register(name: str) -> Callable[[ProviderFactory], ProviderFactory]:
    """Decorator: register *factory* under ``name`` in :data:`REGISTRY`.

    The factory receives ``(channel_name, ChannelConfig)`` and must return
    an object satisfying the :class:`VersionProvider` protocol.
    """

    def _decorator(factory: ProviderFactory) -> ProviderFactory:
        if name in REGISTRY:
            raise ValueError(f"Provider already registered: {name}")
        REGISTRY[name] = factory
        return factory

    return _decorator


def get_provider(channel_name: str, config: ChannelConfig) -> VersionProvider:
    """Instantiate the provider matching ``config.provider``."""
    factory = REGISTRY.get(config.provider)
    if factory is None:
        from core.models import DolCtlError

        raise DolCtlError(
            f"Unsupported provider: {config.provider!r}. "
            f"Known providers: {sorted(REGISTRY)}"
        )
    return factory(channel_name, config)


def known_providers() -> list[str]:
    return sorted(REGISTRY)


# Eagerly import bundled providers so their @register decorators run.
# Imports live at the bottom to avoid a circular import (providers depend
# on core.models, which is already loaded above).
from . import github  # noqa: E402,F401
