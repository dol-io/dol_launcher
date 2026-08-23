from __future__ import annotations

import os
from pathlib import Path
import re
from typing import Any

from core.models import ProgressCallback, RemoteVersion, ValidationError
from infra.net import download_file, fetch_json


_REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")


class GitHubReleasesProvider:
    def __init__(self, channel: str, repository: str, asset_regex: str) -> None:
        if not _REPOSITORY.fullmatch(repository):
            raise ValidationError(
                f"GitHub repository must use owner/name syntax: {repository!r}"
            )
        try:
            pattern = re.compile(asset_regex)
        except re.error as exc:
            raise ValidationError(f"Invalid asset regex: {exc}") from exc
        self.channel = channel
        self.repository = repository
        self.asset_pattern = pattern

    @staticmethod
    def _headers() -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        token = os.environ.get("GITHUB_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _matching_asset(self, assets: Any) -> dict[str, Any] | None:
        if not isinstance(assets, list):
            return None
        for asset in assets:
            if not isinstance(asset, dict):
                continue
            name = str(asset.get("name", ""))
            if self.asset_pattern.fullmatch(name):
                return asset
        return None

    def list_versions(self) -> list[RemoteVersion]:
        url = f"https://api.github.com/repos/{self.repository}/releases?per_page=100"
        payload = fetch_json(url, headers=self._headers())
        if not isinstance(payload, list):
            raise ValueError("GitHub releases response is not an array")

        versions: list[RemoteVersion] = []
        for release in payload:
            if not isinstance(release, dict) or release.get("draft") is True:
                continue
            asset = self._matching_asset(release.get("assets"))
            if asset is None:
                continue
            download_url = str(asset.get("browser_download_url") or "")
            if not download_url:
                continue
            asset_digest = str(asset.get("digest") or "")
            sha256 = (
                asset_digest.removeprefix("sha256:").lower()
                if re.fullmatch(r"sha256:[0-9a-fA-F]{64}", asset_digest)
                else None
            )
            tag = str(release.get("tag_name") or "")
            display_name = str(release.get("name") or tag)
            if not tag and not display_name:
                continue
            versions.append(
                RemoteVersion(
                    id=tag or display_name,
                    display_name=display_name or tag,
                    channel=self.channel,
                    published_at=str(
                        release.get("published_at") or release.get("created_at") or ""
                    ),
                    asset_name=str(asset.get("name") or "download.zip"),
                    download_url=download_url,
                    source_ref=str(release.get("html_url") or ""),
                    sha256=sha256,
                )
            )
        return versions

    def download(
        self,
        version: RemoteVersion,
        destination: Path,
        *,
        progress: ProgressCallback | None = None,
    ) -> str:
        return download_file(
            version.download_url,
            destination,
            headers=self._headers(),
            progress=progress,
            expected_sha256=version.sha256,
        )
