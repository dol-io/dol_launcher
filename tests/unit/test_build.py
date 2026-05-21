from __future__ import annotations

import base64
import json
import re
from pathlib import Path

import pytest

from core.build import _inject_mods_into_html, _MOD_LIST_PATTERN


def _decode_array(html: str) -> list[str]:
    match = re.search(_MOD_LIST_PATTERN, html, re.DOTALL)
    assert match is not None, "modDataValueZipList array not found"
    return json.loads(match.group(1))


class TestInjectModsIntoHtml:
    def test_injects_into_html_with_head(self, tmp_path: Path) -> None:
        html = tmp_path / "index.html"
        html.write_text("<html><head><title>DoL</title></head><body></body></html>")

        mod_a = tmp_path / "a.mod.zip"
        mod_a.write_bytes(b"AAAA")
        _inject_mods_into_html(html, [mod_a])

        content = html.read_text()
        entries = _decode_array(content)
        assert entries == [base64.b64encode(b"AAAA").decode("ascii")]
        # The script block must precede </head>
        assert "</head>" in content
        assert content.index("modDataValueZipList") < content.index("</head>")

    def test_creates_script_when_head_missing(self, tmp_path: Path) -> None:
        html = tmp_path / "x.html"
        html.write_text("<html><body>hi</body></html>")
        mod = tmp_path / "m.mod.zip"
        mod.write_bytes(b"M")
        _inject_mods_into_html(html, [mod])
        entries = _decode_array(html.read_text())
        assert entries == [base64.b64encode(b"M").decode("ascii")]

    def test_appends_to_existing_array(self, tmp_path: Path) -> None:
        existing = base64.b64encode(b"EXISTING").decode("ascii")
        html = tmp_path / "lyra.html"
        html.write_text(
            "<html><head>"
            f'<script>window.modDataValueZipList = ["{existing}"];</script>'
            "</head></html>"
        )
        new_mod = tmp_path / "new.mod.zip"
        new_mod.write_bytes(b"NEW")
        _inject_mods_into_html(html, [new_mod])

        entries = _decode_array(html.read_text())
        assert entries == [existing, base64.b64encode(b"NEW").decode("ascii")]

    def test_multiple_mods_preserved_in_order(self, tmp_path: Path) -> None:
        html = tmp_path / "i.html"
        html.write_text("<html><head></head></html>")
        a = tmp_path / "a.mod.zip"
        b = tmp_path / "b.mod.zip"
        a.write_bytes(b"AA")
        b.write_bytes(b"BB")
        _inject_mods_into_html(html, [a, b])
        entries = _decode_array(html.read_text())
        assert entries == [
            base64.b64encode(b"AA").decode("ascii"),
            base64.b64encode(b"BB").decode("ascii"),
        ]
