from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from infra.log import setup_logging

from .build import build_runtime
from .channel_presets import ChannelPreset, list_presets
from .channels import add_channel, list_channels, remove_channel, update_channel
from .doctor import run_doctor
from .models import (
    BuildResult,
    ChannelConfig,
    DoctorReport,
    InstalledVersion,
    Mod,
    Profile,
    ProgressCallback,
    RemoteVersion,
    RemoveResult,
)
from .mods import add_mod_from_zip, get_mod_info, list_mods, remove_mod
from .profiles import (
    UNSET,
    active_profile_name,
    add_mod_to_profile,
    configure_profile,
    create_profile,
    delete_profile,
    get_profile,
    list_profiles,
    remove_mod_from_profile,
    reorder_mods,
    select_profile,
    set_profile_mods,
)
from .root import RootLayout, init_root, load_state, resolve_root
from .run import LaunchSession, prepare_run, prepare_serve
from .versions import (
    get_installed,
    install_from_dir,
    install_from_file,
    install_from_remote,
    list_installed,
    list_remote_versions,
    remove_version,
)


@dataclass(frozen=True, slots=True)
class LauncherSnapshot:
    active_profile: str
    profiles: tuple[Profile, ...]
    versions: tuple[InstalledVersion, ...]
    mods: tuple[Mod, ...]
    channels: tuple[tuple[str, ChannelConfig], ...]


class Launcher:
    """Public application facade shared by the CLI and Textual TUI."""

    def __init__(self, root: Path) -> None:
        self.layout = RootLayout.open(root)

    @classmethod
    def open(cls, root: str | Path | None = None) -> "Launcher":
        return cls(resolve_root(root))

    @classmethod
    def initialise(cls, root: Path) -> "Launcher":
        return cls(init_root(root).root)

    @property
    def root(self) -> Path:
        return self.layout.root

    def configure_logging(self, *, verbose: bool = False) -> None:
        setup_logging(self.root, verbose=verbose)

    def snapshot(self) -> LauncherSnapshot:
        state = load_state(self.root)
        return LauncherSnapshot(
            active_profile=state.active_profile,
            profiles=tuple(list_profiles(self.root)),
            versions=tuple(list_installed(self.root)),
            mods=tuple(list_mods(self.root)),
            channels=tuple(list_channels(self.root)),
        )

    def active_instance(self, requested: str | None = None) -> str:
        return active_profile_name(self.root, requested)

    def instances(self) -> list[Profile]:
        return list_profiles(self.root)

    def instance(self, name: str | None = None) -> Profile:
        return get_profile(self.root, self.active_instance(name))

    def create_instance(self, name: str, *, version_id: str | None = None) -> Profile:
        return create_profile(self.root, name, version_id=version_id)

    def select_instance(self, name: str) -> Profile:
        return select_profile(self.root, name)

    def configure_instance(
        self,
        name: str,
        *,
        version_id: str | None | object = UNSET,
        port: int | None | object = UNSET,
        open_browser: bool | None | object = UNSET,
    ) -> Profile:
        return configure_profile(
            self.root,
            name,
            version_id=version_id,
            port=port,
            open_browser=open_browser,
        )

    def delete_instance(self, name: str) -> RemoveResult:
        return delete_profile(self.root, name)

    def enable_mod(self, instance: str, mod_id: str) -> Profile:
        return add_mod_to_profile(self.root, instance, mod_id)

    def disable_mod(self, instance: str, mod_id: str) -> Profile:
        return remove_mod_from_profile(self.root, instance, mod_id)

    def reorder_instance_mods(self, instance: str, mod_ids: list[str]) -> Profile:
        return reorder_mods(self.root, instance, mod_ids)

    def set_instance_mods(self, instance: str, mod_ids: list[str]) -> Profile:
        return set_profile_mods(self.root, instance, mod_ids)

    def versions(self) -> list[InstalledVersion]:
        return list_installed(self.root)

    def version(self, version_id: str) -> InstalledVersion:
        return get_installed(self.root, version_id)

    def remote_versions(
        self, channel: str, *, refresh: bool = False
    ) -> list[RemoteVersion]:
        return list_remote_versions(self.root, channel, refresh=refresh)

    def install_version_file(
        self,
        source: Path,
        *,
        version_id: str | None = None,
        channel: str = "local",
        force: bool = False,
    ) -> str:
        return install_from_file(
            self.root,
            source,
            version_id,
            channel,
            force=force,
        )

    def install_version_directory(
        self,
        source: Path,
        *,
        version_id: str | None = None,
        channel: str = "local",
        force: bool = False,
    ) -> str:
        return install_from_dir(
            self.root,
            source,
            version_id,
            channel,
            force=force,
        )

    def install_remote_version(
        self,
        channel: str,
        selector: str = "latest",
        *,
        force: bool = False,
        progress: ProgressCallback | None = None,
    ) -> str:
        return install_from_remote(
            self.root,
            channel,
            selector,
            force=force,
            progress=progress,
        )

    def remove_version(self, version_id: str, *, force: bool = False) -> RemoveResult:
        return remove_version(self.root, version_id, force=force)

    def mods(self) -> list[Mod]:
        return list_mods(self.root)

    def mod(self, mod_id: str) -> Mod:
        return get_mod_info(self.root, mod_id)

    def install_mod(
        self,
        source: str,
        *,
        mod_id: str | None = None,
        force: bool = False,
        progress: ProgressCallback | None = None,
    ) -> str:
        return add_mod_from_zip(
            self.root,
            source,
            mod_id,
            force=force,
            progress=progress,
        )

    def remove_mod(self, mod_id: str) -> RemoveResult:
        return remove_mod(self.root, mod_id)

    def channels(self) -> list[tuple[str, ChannelConfig]]:
        return list_channels(self.root)

    @staticmethod
    def channel_presets() -> list[tuple[str, ChannelPreset]]:
        return list_presets()

    def add_channel(self, name: str, **fields: object) -> ChannelConfig:
        return add_channel(self.root, name, **fields)  # type: ignore[arg-type]

    def update_channel(self, name: str, **fields: object) -> ChannelConfig:
        return update_channel(self.root, name, **fields)  # type: ignore[arg-type]

    def remove_channel(self, name: str) -> None:
        remove_channel(self.root, name)

    def build(self, instance: str | None = None, *, clean: bool = False) -> BuildResult:
        name = self.active_instance(instance)
        return build_runtime(self.root, name, clean=clean)

    def prepare_run(
        self,
        instance: str | None = None,
        *,
        port: int | None = None,
        open_browser: bool | None = None,
        allow_lan: bool = False,
        clean: bool = False,
    ) -> LaunchSession:
        return prepare_run(
            self.root,
            instance,
            port,
            open_browser,
            allow_lan=allow_lan,
            clean=clean,
        )

    def prepare_serve(
        self,
        instance: str | None = None,
        *,
        port: int | None = None,
        allow_lan: bool = False,
    ) -> LaunchSession:
        return prepare_serve(
            self.root,
            instance,
            port,
            allow_lan=allow_lan,
        )

    def doctor(self) -> DoctorReport:
        return run_doctor(self.root)
