from __future__ import annotations

from pathlib import Path

from .core_build import build_runtime
from .core_profiles import get_profile
from .core_root import load_config
from .core_serve import create_server
from .models import RunResult


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

    url = f"http://127.0.0.1:{actual_port}/"
    return RunResult(
        profile=profile_name,
        url=url,
        port=actual_port,
        output_dir=build_result.output_dir,
        server=server,
        open_browser=open_browser,
    )
