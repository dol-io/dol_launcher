from __future__ import annotations

from pathlib import Path

import pytest

from core.models import DolCtlError
from core.profiles import (
    add_mod_to_profile,
    create_profile,
    get_profile,
    list_profiles,
    remove_mod_from_profile,
    reorder_mods,
    set_active_profile,
    set_profile_version,
)


def _make_fake_mod(root: Path, mod_id: str) -> None:
    mod_dir = root / "mods" / mod_id
    mod_dir.mkdir(parents=True, exist_ok=True)
    (mod_dir / ".mod.toml").write_text(f'id = "{mod_id}"\n', encoding="utf-8")
    (mod_dir / f"{mod_id}.mod.zip").write_bytes(b"")


def _make_fake_version(root: Path, version_id: str) -> None:
    version_dir = root / "versions" / version_id
    version_dir.mkdir(parents=True, exist_ok=True)
    (version_dir / ".manifest.toml").write_text("", encoding="utf-8")


class TestProfileBasics:
    def test_default_profile_exists_after_init(self, root: Path) -> None:
        assert "default" in list_profiles(root)

    def test_create_and_list(self, root: Path) -> None:
        create_profile(root, "alt")
        assert sorted(list_profiles(root)) == ["alt", "default"]

    def test_create_rejects_duplicate(self, root: Path) -> None:
        create_profile(root, "alt")
        with pytest.raises(DolCtlError):
            create_profile(root, "alt")

    def test_set_active(self, root: Path) -> None:
        create_profile(root, "alt")
        set_active_profile(root, "alt")
        from core.root import load_state

        assert load_state(root).active_profile == "alt"

    def test_set_version_requires_existing_version(self, root: Path) -> None:
        with pytest.raises(DolCtlError):
            set_profile_version(root, "default", "nonexistent")

    def test_set_version_updates_profile_and_state(self, root: Path) -> None:
        _make_fake_version(root, "vX")
        set_profile_version(root, "default", "vX")
        assert get_profile(root, "default").version_id == "vX"
        from core.root import load_state

        assert load_state(root).last_used_version == "vX"


class TestModOrder:
    def test_add_and_remove(self, root: Path) -> None:
        _make_fake_mod(root, "a")
        _make_fake_mod(root, "b")
        add_mod_to_profile(root, "default", "a")
        add_mod_to_profile(root, "default", "b")
        assert get_profile(root, "default").mod_order == ["a", "b"]
        remove_mod_from_profile(root, "default", "a")
        assert get_profile(root, "default").mod_order == ["b"]

    def test_add_rejects_unknown_mod(self, root: Path) -> None:
        with pytest.raises(DolCtlError):
            add_mod_to_profile(root, "default", "ghost")

    def test_add_rejects_duplicate(self, root: Path) -> None:
        _make_fake_mod(root, "a")
        add_mod_to_profile(root, "default", "a")
        with pytest.raises(DolCtlError):
            add_mod_to_profile(root, "default", "a")

    def test_reorder_must_be_a_permutation(self, root: Path) -> None:
        _make_fake_mod(root, "a")
        _make_fake_mod(root, "b")
        add_mod_to_profile(root, "default", "a")
        add_mod_to_profile(root, "default", "b")

        # Same set: OK
        reorder_mods(root, "default", ["b", "a"])
        assert get_profile(root, "default").mod_order == ["b", "a"]

        # Missing one: rejected
        with pytest.raises(DolCtlError):
            reorder_mods(root, "default", ["a"])

        # Extra one: rejected
        with pytest.raises(DolCtlError):
            reorder_mods(root, "default", ["a", "b", "c"])
