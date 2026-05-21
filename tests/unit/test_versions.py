from __future__ import annotations

import pytest

from core.models import RemoteVersion
from core.versions import (
    _make_version_id,
    _normalize_id,
    _resolve_selector,
    _select_remote_version,
)


def _rv(id: str, published: str = "2024-01-01T00:00:00Z") -> RemoteVersion:
    return RemoteVersion(
        id=id,
        display_name=id,
        channel="vanilla",
        published_at=published,
        asset_name=f"{id}.zip",
        download_url=f"https://example.com/{id}.zip",
        source_ref="",
    )


class TestNormalizeId:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("0.5.3", "0.5.3"),
            ("v0.5.3", "0.5.3"),
        ],
    )
    def test_strips_leading_v(self, raw: str, expected: str) -> None:
        assert _normalize_id(raw) == expected

    def test_known_quirk_strips_any_leading_v(self) -> None:
        # Documents existing behavior: any leading 'v' is stripped, even
        # when it's part of an unrelated word. Filed as a follow-up.
        assert _normalize_id("vanilla-0.5.3") == "anilla-0.5.3"


class TestSelectRemoteVersion:
    def test_latest_picks_highest_published(self) -> None:
        versions = [
            _rv("0.5.3", "2024-01-01T00:00:00Z"),
            _rv("0.5.5", "2024-03-01T00:00:00Z"),
            _rv("0.5.4", "2024-02-01T00:00:00Z"),
        ]
        chosen = _select_remote_version(versions, "latest")
        assert chosen.id == "0.5.5"

    def test_explicit_id_match(self) -> None:
        versions = [_rv("0.5.3"), _rv("0.5.4")]
        chosen = _select_remote_version(versions, "0.5.3")
        assert chosen.id == "0.5.3"

    def test_v_prefix_equivalence(self) -> None:
        versions = [_rv("0.5.3"), _rv("0.5.4")]
        chosen = _select_remote_version(versions, "v0.5.3")
        assert chosen.id == "0.5.3"

    def test_missing_raises(self) -> None:
        from core.models import DolCtlError

        with pytest.raises(DolCtlError):
            _select_remote_version([_rv("0.5.3")], "9.9.9")


class TestResolveSelector:
    def test_no_channel_prefix_uses_default(self) -> None:
        assert _resolve_selector("latest", "vanilla") == ("vanilla", "latest")
        assert _resolve_selector("0.5.3", "vanilla") == ("vanilla", "0.5.3")

    def test_channel_prefix_overrides_default(self) -> None:
        assert _resolve_selector("variant_plus:latest", "vanilla") == (
            "variant_plus",
            "latest",
        )

    def test_empty_channel_falls_back_to_default(self) -> None:
        assert _resolve_selector(":latest", "vanilla") == ("vanilla", ":latest")


class TestMakeVersionId:
    def test_prepends_channel_when_absent(self) -> None:
        assert _make_version_id("vanilla", "0.5.3") == "vanilla-0.5.3"

    def test_idempotent_when_already_prefixed(self) -> None:
        assert _make_version_id("vanilla", "vanilla-0.5.3") == "vanilla-0.5.3"
