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


@dataclass(frozen=True)
class ChannelPreset:
    provider: str
    repo: str
    asset_regex: str
    description: str = ""


PRESETS: dict[str, ChannelPreset] = {
    "dol-vanilla": ChannelPreset(
        provider="github",
        repo="Vrelnir/degrees-of-lewdity",
        # Vanilla releases ship the Twine HTML inside a versioned zip
        # named "Degrees of Lewdity VERSION.zip".
        asset_regex=r"Degrees of Lewdity.*\.zip",
        description="Vanilla Degrees of Lewdity releases from Vrelnir.",
    ),
    "dol-modloader": ChannelPreset(
        provider="github",
        repo="Lyoko-Jeremie/sugarcube-2-ModLoader",
        # ModLoader-flavoured DoL bundles; filename pattern varies by
        # release, so the regex is intentionally a touch loose.
        asset_regex=r"DoL-ModLoader.*\.zip",
        description="DoL with the SugarCube-2 ModLoader pre-applied.",
    ),
}


def get_preset(key: str) -> ChannelPreset:
    if key not in PRESETS:
        raise KeyError(key)
    return PRESETS[key]


def list_presets() -> list[tuple[str, ChannelPreset]]:
    return sorted(PRESETS.items())
