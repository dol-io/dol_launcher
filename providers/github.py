from __future__ import annotations

import os
import re
from typing import Any

from infra.net import fetch_json
from core.models import RemoteVersion


class GitHubReleasesProvider:
    def __init__(self, channel: str, repo: str, asset_regex: str) -> None:
        self.channel = channel
        self.repo = repo
        self.asset_pattern = re.compile(asset_regex)

    def _headers(self) -> dict[str, str] | None:
        token = os.environ.get("GITHUB_TOKEN")
        if not token:
            return None
        return {"Authorization": f"Bearer {token}"}

    def list_versions(self) -> list[RemoteVersion]:
        url = f"https://api.github.com/repos/{self.repo}/releases?per_page=30"
        data = fetch_json(url, headers=self._headers())
        versions: list[RemoteVersion] = []
        for release in data:
            asset = self._select_asset(release.get("assets", []))
            if asset is None:
                continue
            tag = str(release.get("tag_name") or "")
            name = str(release.get("name") or tag)
            published_at = str(release.get("published_at") or release.get("created_at") or "")
            versions.append(
                RemoteVersion(
                    id=tag or name,
                    display_name=name or tag,
                    channel=self.channel,
                    published_at=published_at,
                    asset_name=str(asset.get("name", "")),
                    download_url=str(asset.get("browser_download_url", "")),
                    source_ref=str(release.get("html_url", "")),
                )
            )
        return versions

    def _select_asset(self, assets: list[dict[str, Any]]) -> dict[str, Any] | None:
        for asset in assets:
            name = str(asset.get("name", ""))
            if self.asset_pattern.match(name):
                return asset
        return None
