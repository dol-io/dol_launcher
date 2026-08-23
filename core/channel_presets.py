"""Built-in channel presets.

A *preset* is a known-good ChannelConfig template keyed by short name.
``dolctl channel add <name> --preset <key>`` materialises one in the user
config without forcing them to remember the right ``repo`` / regex.

Presets are intentionally a static dict; updates ship with new releases
rather than being fetched live. Tweak the entries here when the upstream
projects change layout.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import ChannelKind


@dataclass(frozen=True)
class ChannelPreset:
    kind: ChannelKind
    provider: str
    repo: str
    asset_regex: str
    description: str = ""


PRESETS: dict[str, ChannelPreset] = {
    "dol-modloader": ChannelPreset(
        kind="game",
        provider="github",
        repo="Lyoko-Jeremie/DoLModLoaderBuild",
        # Each release ships ``DoL-ModLoader-<modloader-ver>-dol-<game-ver>-<sha>.zip``
        # plus an image pack mod we don't want to install as the game.
        asset_regex=r"DoL-ModLoader-.*\.zip",
        description="DoL with the SugarCube-2 ModLoader pre-applied.",
    ),
    "dol-modloader-zh": ChannelPreset(
        kind="game",
        provider="github",
        repo="Eltirosto/Degrees-of-Lewdity-Chinese-Localization",
        # Prefer the normal browser build over the legacy polyfill build.
        asset_regex=r"DoL-ModLoader-(?!.*-polyfill\.zip$).*\.zip",
        description="Chinese-localised DoL with ModLoader.",
    ),
    "dol-image-pack": ChannelPreset(
        kind="mod",
        provider="github",
        repo="Lyoko-Jeremie/DoLModLoaderBuild",
        asset_regex=r"GameOriginalImagePack\.mod\.zip",
        description="Original image pack for ModLoader builds.",
    ),
    "dol-i18n-zh": ChannelPreset(
        kind="mod",
        provider="github",
        repo="Eltirosto/Degrees-of-Lewdity-Chinese-Localization",
        asset_regex=r"ModI18N-.*\.mod\.zip",
        description="Chinese localisation Mod for ModLoader builds.",
    ),
    "doli": ChannelPreset(
        kind="mod",
        provider="github",
        repo="ArsNativa/Degrees-of-Lewdity-Intelligence",
        asset_regex=r"DOLI\.mod\.zip",
        description="Degrees of Lewdity Intelligence Mod.",
    ),
}


def get_preset(key: str) -> ChannelPreset:
    if key not in PRESETS:
        raise KeyError(key)
    return PRESETS[key]


def list_presets() -> list[tuple[str, ChannelPreset]]:
    return sorted(PRESETS.items())
