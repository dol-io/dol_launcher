from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from infra.open import open_browser

from .build import BUILD_META_SCHEMA, build_runtime, expected_build_key
from .models import BuildResult, DataError, NotFoundError
from .profiles import active_profile_name, get_profile
from .root import RootLayout, load_config, validate_port
from .serve import ServerHandle, create_server
from .versions import get_installed


@dataclass(slots=True)
class LaunchSession:
    profile: str
    build: BuildResult | None
    server: ServerHandle
    should_open_browser: bool

    @property
    def url(self) -> str:
        return self.server.url

    @property
    def port(self) -> int:
        return self.server.port

    @property
    def output_dir(self) -> Path:
        return self.server.directory

    def open_browser(self) -> bool:
        return open_browser(self.url, enabled=self.should_open_browser)

    def start(self) -> None:
        self.server.start()

    def serve_forever(self) -> None:
        self.server.serve_forever()

    def close(self) -> None:
        self.server.close()

    def stop(self) -> None:
        self.server.stop()


def _launch_settings(
    root: Path,
    profile_name: str | None,
    port_override: int | None,
    browser_override: bool | None,
) -> tuple[str, int, bool, bool]:
    name = active_profile_name(root, profile_name)
    profile = get_profile(root, name)
    config = load_config(root)

    if port_override is not None:
        port = validate_port(port_override)
        allow_fallback = False
    elif profile.port is not None:
        port = validate_port(profile.port)
        allow_fallback = True
    else:
        port = validate_port(config.default_port)
        allow_fallback = True

    should_open = config.open_browser
    if profile.open_browser is not None:
        should_open = profile.open_browser
    if browser_override is not None:
        should_open = browser_override
    return name, port, allow_fallback, should_open


def prepare_run(
    root: Path,
    profile_name: str | None = None,
    port_override: int | None = None,
    open_browser_override: bool | None = None,
    *,
    allow_lan: bool = False,
    clean: bool = False,
) -> LaunchSession:
    layout = RootLayout.open(root)
    name, port, allow_fallback, should_open = _launch_settings(
        layout.root,
        profile_name,
        port_override,
        open_browser_override,
    )
    result = build_runtime(layout.root, name, clean=clean)
    host = "0.0.0.0" if allow_lan else "127.0.0.1"
    server = create_server(
        result.output_dir,
        host=host,
        port=port,
        allow_fallback=allow_fallback,
        entry_name=result.entry,
        allow_lan=allow_lan,
    )
    return LaunchSession(name, result, server, should_open)


def prepare_serve(
    root: Path,
    profile_name: str | None = None,
    port_override: int | None = None,
    *,
    allow_lan: bool = False,
) -> LaunchSession:
    layout = RootLayout.open(root)
    name, port, allow_fallback, _should_open = _launch_settings(
        layout.root,
        profile_name,
        port_override,
        False,
    )
    profile = get_profile(layout.root, name)
    if not profile.version_id:
        raise NotFoundError(f"Instance has no version selected: {name}")
    version = get_installed(layout.root, profile.version_id)
    runtime = layout.runtime_dir(name)
    metadata = runtime / "build_meta.json"
    try:
        payload = json.loads(metadata.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError) as exc:
        raise NotFoundError(
            f"Instance {name} has not been built; run dolctl build first"
        ) from exc
    expected_key = expected_build_key(layout.root, name)
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != BUILD_META_SCHEMA
        or payload.get("base_version_id") != version.id
        or payload.get("build_key") != expected_key
    ):
        raise DataError(f"Runtime for {name} is stale; build it again")
    entry = str(payload.get("entry") or version.entry)
    host = "0.0.0.0" if allow_lan else "127.0.0.1"
    server = create_server(
        runtime / "merged",
        host=host,
        port=port,
        allow_fallback=allow_fallback,
        entry_name=entry,
        allow_lan=allow_lan,
    )
    return LaunchSession(name, None, server, False)
