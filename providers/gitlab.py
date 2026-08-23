from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
from urllib.parse import urlencode

from core.models import ProgressCallback
from infra.net import download_file, fetch_json


_COMMIT_ID = re.compile(r"[0-9a-fA-F]{7,64}")


@dataclass(frozen=True, slots=True)
class GitLabCommit:
    id: str
    short_id: str
    committed_date: str
    title: str
    web_url: str


class GitLabRepositoryProvider:
    """Small GitLab repository API adapter used by reviewed imagepack recipes."""

    def __init__(self, base_url: str, project_id: int, project_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.project_id = project_id
        self.project_url = project_url.rstrip("/")

    @staticmethod
    def _headers() -> dict[str, str]:
        headers = {"Accept": "application/json"}
        token = os.environ.get("GITLAB_TOKEN")
        if token:
            headers["PRIVATE-TOKEN"] = token
        return headers

    def latest_commit(self, ref: str, path: str) -> GitLabCommit:
        query = urlencode(
            {"ref_name": ref, "path": path, "per_page": "1"}
        )
        url = (
            f"{self.base_url}/api/v4/projects/{self.project_id}"
            f"/repository/commits?{query}"
        )
        payload = fetch_json(url, headers=self._headers())
        if not isinstance(payload, list) or not payload:
            raise ValueError(f"No commits found for {path!r} on {ref!r}")
        raw = payload[0]
        if not isinstance(raw, dict):
            raise ValueError("GitLab commits response has an invalid entry")
        commit_id = str(raw.get("id") or "")
        if not _COMMIT_ID.fullmatch(commit_id):
            raise ValueError("GitLab commit response has no valid commit id")
        short_id = str(raw.get("short_id") or commit_id[:8])
        if not _COMMIT_ID.fullmatch(short_id):
            short_id = commit_id[:8]
        return GitLabCommit(
            id=commit_id.lower(),
            short_id=short_id.lower(),
            committed_date=str(raw.get("committed_date") or ""),
            title=str(raw.get("title") or ""),
            web_url=str(
                raw.get("web_url")
                or f"{self.project_url}/-/commit/{commit_id}"
            ),
        )

    def download_archive(
        self,
        commit: GitLabCommit,
        path: str,
        destination: Path,
        *,
        progress: ProgressCallback | None = None,
    ) -> str:
        query = urlencode({"sha": commit.id, "path": path})
        url = (
            f"{self.base_url}/api/v4/projects/{self.project_id}"
            f"/repository/archive.tar.gz?{query}"
        )
        return download_file(
            url,
            destination,
            headers=self._headers(),
            progress=progress,
        )
