from __future__ import annotations

from pathlib import Path

import pytest

from core.launcher import Launcher
from core.models import ConflictError, NotFoundError, ValidationError
from core.root import load_state


def _install_game(launcher: Launcher, source: Path, version_id: str = "game") -> None:
    launcher.install_version_directory(source, version_id=version_id)


def test_instance_lifecycle_and_settings(launcher: Launcher, make_version_dir) -> None:
    _install_game(launcher, make_version_dir())
    created = launcher.create_instance("casual", version_id="game")
    assert created.version_id == "game"
    launcher.select_instance("casual")
    configured = launcher.configure_instance("casual", port=9000, open_browser=False)
    assert configured.port == 9000
    assert configured.open_browser is False
    assert launcher.active_instance() == "casual"


def test_default_instance_cannot_be_deleted(launcher: Launcher) -> None:
    with pytest.raises(ConflictError, match="default"):
        launcher.delete_instance("default")


def test_deleting_active_instance_selects_default_and_removes_runtime(
    launcher: Launcher,
) -> None:
    launcher.create_instance("temporary")
    launcher.select_instance("temporary")
    runtime = launcher.root / "runtime" / "temporary"
    runtime.mkdir(parents=True)
    launcher.delete_instance("temporary")
    assert load_state(launcher.root).active_profile == "default"
    assert not runtime.exists()


def test_instance_requires_existing_version(launcher: Launcher) -> None:
    with pytest.raises(NotFoundError, match="Version not found"):
        launcher.create_instance("broken", version_id="missing")


@pytest.mark.parametrize("name", ["../../outside", "/tmp/outside", r"..\outside"])
def test_instance_names_cannot_escape_root(launcher: Launcher, name: str) -> None:
    with pytest.raises(ValidationError):
        launcher.create_instance(name)


def test_mod_enable_disable_and_reorder(launcher: Launcher, make_mod_zip) -> None:
    alpha = launcher.install_mod(str(make_mod_zip("alpha.zip", mod_name="Alpha")))
    beta = launcher.install_mod(str(make_mod_zip("beta.zip", mod_name="Beta")))
    launcher.enable_mod("default", alpha)
    launcher.enable_mod("default", beta)
    assert launcher.instance("default").mod_order == [alpha, beta]
    launcher.reorder_instance_mods("default", [beta, alpha])
    assert launcher.instance("default").mod_order == [beta, alpha]
    launcher.disable_mod("default", beta)
    assert launcher.instance("default").mod_order == [alpha]


def test_reorder_must_be_exact_permutation(launcher: Launcher, make_mod_zip) -> None:
    mod_id = launcher.install_mod(str(make_mod_zip()))
    launcher.enable_mod("default", mod_id)
    with pytest.raises(ValidationError, match="exactly"):
        launcher.reorder_instance_mods("default", [])


def test_set_instance_mods_replaces_selection_atomically(
    launcher: Launcher, make_mod_zip
) -> None:
    alpha = launcher.install_mod(str(make_mod_zip("alpha.zip", mod_name="Alpha")))
    beta = launcher.install_mod(str(make_mod_zip("beta.zip", mod_name="Beta")))
    launcher.enable_mod("default", alpha)

    updated = launcher.set_instance_mods("default", [beta])
    assert updated.mod_order == [beta]

    with pytest.raises(NotFoundError, match="missing"):
        launcher.set_instance_mods("default", ["missing"])
    assert launcher.instance("default").mod_order == [beta]
