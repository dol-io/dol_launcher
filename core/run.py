from __future__ import annotations

from pathlib import Path

from .build import build_runtime
from .profiles import get_profile
from .root import load_config
from .serve import create_server
from core.models import RunResult
from infra.toml import read_toml
from core.models import version_manifest_from_dict


def prepare_run(
    root: Path,
    profile_name: str,
    port_override: int | None,
    open_browser_override: bool | None,
) -> RunResult:
    config = load_config(root)
    profile = get_profile(root, profile_name)
    build_result = build_runtime(root, profile_name, clean=True)

    if port_override is not None:
        port = port_override
        allow_fallback = False
    elif profile.port is not None:
        port = profile.port
        allow_fallback = True
    else:
        port = config.default_port
        allow_fallback = True

    server, actual_port = create_server(
        build_result.output_dir,
        host="127.0.0.1",
        port=port,
        allow_fallback=allow_fallback,
    )

    open_browser = config.open_browser
    if profile.open_browser is not None:
        open_browser = profile.open_browser
    if open_browser_override is not None:
        open_browser = open_browser_override

    # Determine the entry HTML filename from the version manifest
    manifest_path = (root / "versions" / profile.version_id / ".manifest.toml")
    entry_name = "index.html"
    if manifest_path.exists():
        vm = version_manifest_from_dict(read_toml(manifest_path))
        entry_name = vm.entry
    url = f"http://127.0.0.1:{actual_port}/{entry_name}"
    return RunResult(
        profile=profile_name,
        url=url,
        port=actual_port,
        output_dir=build_result.output_dir,
        server=server,
        open_browser=open_browser,
    )
