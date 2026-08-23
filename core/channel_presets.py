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
    "dol-lyra-besc-ucb": ChannelPreset(
        kind="game",
        provider="github",
        repo="DoL-Lyra/Lyra",
        # Lyra publishes complete game builds, not standalone ModLoader Mods.
        asset_regex=r"DoL-.*-Lyra-.*-besc-ucb-.*\.zip",
        description="Lyra complete game build with BESC and UCB (not a Mod).",
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
    "cheat-lyra": ChannelPreset(
        kind="mod",
        provider="github",
        repo="DoL-Lyra/Cheat",
        asset_regex=r"Cheat-Lyra-v.*\.mod\.zip",
        description="Lyra cheat and feat-unlock Mod.",
    ),
    "combat-status-display-lyra": ChannelPreset(
        kind="mod",
        provider="github",
        repo="DoL-Lyra/CombatStatusDisplay",
        asset_regex=r"CombatStatusDisplay-Lyra-v.*\.mod\.zip",
        description="Lyra enemy HP and AP display Mod.",
    ),
    "au-female-v0.8.7-dol-0.5.8.9": ChannelPreset(
        kind="mod",
        provider="github",
        repo="AOKIUTAGE/UTAGEsDOL3.0",
        asset_regex=r"AUfemale\.model_v0\.8\.7\.zip",
        description="AU female model v0.8.7 — DoL 0.5.8.9.",
    ),
    "au-female-v0.9.3-dol-0.5.9": ChannelPreset(
        kind="mod",
        provider="github",
        repo="AOKIUTAGE/UTAGEsDOL3.0",
        asset_regex=r"AUfemale\.model_v0\.9\.3\.zip",
        description="AU female model v0.9.3 — DoL 0.5.9.",
    ),
    "au-male-v0.3.7-dol-0.5.8.9": ChannelPreset(
        kind="mod",
        provider="github",
        repo="AOKIUTAGE/UTAGEsDOL3.0",
        asset_regex=r"AUmale\.model_v0\.3\.7\.zip",
        description="AU male model v0.3.7 — DoL 0.5.8.9.",
    ),
    "au-male-v0.4.2-dol-0.5.9": ChannelPreset(
        kind="mod",
        provider="github",
        repo="AOKIUTAGE/UTAGEsDOL3.0",
        asset_regex=r"AUmale\.model_v0\.4\.2\.zip",
        description="AU male model v0.4.2 — DoL 0.5.9.",
    ),
    "au-androgynous-v0.0.7-dol-0.5.8.9": ChannelPreset(
        kind="mod",
        provider="github",
        repo="AOKIUTAGE/UTAGEsDOL3.0",
        asset_regex=r"AUandrogynous\.model_v0\.0\.7\.zip",
        description="AU androgynous model v0.0.7 — DoL 0.5.8.9.",
    ),
    "au-androgynous-v0.1.1-dol-0.5.9": ChannelPreset(
        kind="mod",
        provider="github",
        repo="AOKIUTAGE/UTAGEsDOL3.0",
        asset_regex=r"AUandrogynous\.model_v0\.1\.1\.zip",
        description="AU androgynous model v0.1.1 — DoL 0.5.9.",
    ),
    "ausdol-facial-expansion": ChannelPreset(
        kind="mod",
        provider="github",
        repo="AOKIUTAGE/UTAGEsDOL3.0",
        asset_regex=r"AUsDoL\.facial\.expansion\.mod\.zip",
        description="AUsDoL facial expansion Mod.",
    ),
}


def get_preset(key: str) -> ChannelPreset:
    if key not in PRESETS:
        raise KeyError(key)
    return PRESETS[key]


def list_presets(kind: ChannelKind | None = None) -> list[tuple[str, ChannelPreset]]:
    return sorted(
        (key, preset)
        for key, preset in PRESETS.items()
        if kind is None or preset.kind == kind
    )
