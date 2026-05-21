from __future__ import annotations

import json
import warnings
import zipfile
from pathlib import Path

import pytest

from core.mods import (
    _read_boot_json,
    _slugify_mod_id,
    add_mod_from_zip,
    get_mod_info,
    list_mods,
    remove_mod,
)
from core.models import DolCtlError


class TestSlugifyModId:
    @pytest.mark.parametrize(
        "name,expected",
        [
            ("My Mod", "my_mod"),
            ("CamelCase", "camelcase"),
            ("with-dash", "with-dash"),
            ("  spaces  ", "spaces"),
            ("a/b*c", "a_b_c"),
        ],
    )
    def test_ascii_slug(self, name: str, expected: str) -> None:
        assert _slugify_mod_id(name) == expected

    def test_cjk_degrades_to_seed_plus_hash(self) -> None:
        slug = _slugify_mod_id("通用战斗美化", fallback_seed="zed-fix")
        # Slug should start with the ASCII-slugified seed, and include a hash suffix
        # so two different CJK names with the same seed still differ.
        assert slug.startswith("zed-fix-")
        assert len(slug) > len("zed-fix-")

    def test_cjk_without_seed_falls_back_to_mod(self) -> None:
        slug = _slugify_mod_id("通用战斗美化")
        assert slug.startswith("mod-")

    def test_distinct_cjk_names_get_distinct_ids(self) -> None:
        a = _slugify_mod_id("第一", fallback_seed="seed")
        b = _slugify_mod_id("第二", fallback_seed="seed")
        assert a != b


class TestReadBootJson:
    def test_returns_boot_at_root(self, tmp_path: Path) -> None:
        zip_path = tmp_path / "m.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("boot.json", json.dumps({"name": "X", "version": "1"}))
        boot = _read_boot_json(zip_path)
        assert boot == {"name": "X", "version": "1"}

    def test_returns_boot_inside_wrapper_dir(self, tmp_path: Path) -> None:
        zip_path = tmp_path / "m.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("wrapper/boot.json", json.dumps({"name": "Y"}))
        boot = _read_boot_json(zip_path)
        assert boot == {"name": "Y"}

    def test_returns_none_when_missing(self, tmp_path: Path) -> None:
        zip_path = tmp_path / "m.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("readme.txt", "hi")
        assert _read_boot_json(zip_path) is None


class TestAddModFromZip:
    def test_imports_mod_with_boot_metadata(self, root: Path, make_mod_zip) -> None:
        zip_path = make_mod_zip(
            "sample.mod.zip",
            boot={"name": "Sample", "version": "0.1.0", "author": "alice"},
        )
        mod_id = add_mod_from_zip(root, str(zip_path))
        assert mod_id == "sample"

        info = get_mod_info(root, mod_id)
        assert info.name == "Sample"
        assert info.version == "0.1.0"
        assert info.author == "alice"
        assert (root / "mods" / mod_id / "sample.mod.zip").exists()

    def test_rejects_duplicate_without_force(self, root: Path, make_mod_zip) -> None:
        zip_path = make_mod_zip("a.mod.zip", boot={"name": "A", "version": "1"})
        add_mod_from_zip(root, str(zip_path))
        with pytest.raises(DolCtlError):
            add_mod_from_zip(root, str(zip_path))

    def test_force_overwrites_existing(self, root: Path, make_mod_zip) -> None:
        first = make_mod_zip("a.mod.zip", boot={"name": "A", "version": "1"})
        add_mod_from_zip(root, str(first))
        second = make_mod_zip(
            "a.mod.zip", boot={"name": "A", "version": "2"}
        )
        add_mod_from_zip(root, str(second), force=True)
        assert get_mod_info(root, "a").version == "2"

    def test_warns_when_no_boot_json(self, root: Path, make_mod_zip) -> None:
        zip_path = make_mod_zip("noboot.mod.zip", boot=None, extra={"x.txt": b"x"})
        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter("always")
            mod_id = add_mod_from_zip(root, str(zip_path))
        assert any("boot.json" in str(w.message) for w in captured)
        assert get_mod_info(root, mod_id).version == ""

    def test_list_and_remove(self, root: Path, make_mod_zip) -> None:
        zip_a = make_mod_zip("a.mod.zip", boot={"name": "A", "version": "1"})
        zip_b = make_mod_zip("b.mod.zip", boot={"name": "B", "version": "1"})
        add_mod_from_zip(root, str(zip_a))
        add_mod_from_zip(root, str(zip_b))

        ids = [m.id for m in list_mods(root)]
        assert ids == ["a", "b"]

        remove_mod(root, "a")
        assert [m.id for m in list_mods(root)] == ["b"]
