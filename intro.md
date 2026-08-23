# dolctl — product specification

## 1. Product direction

`dolctl` is a small, local Degrees of Lewdity launcher built with Python 3.11.
Its interaction model follows the useful part of Prism Launcher: users manage
named **instances**, and each instance owns a game version, an ordered mod set,
and launch preferences. A user should normally be able to select an instance
and press Launch without thinking about build directories or HTTP servers.

Both interfaces are first-class:

- the Typer CLI is scriptable and remains usable without importing Textual;
- the Textual TUI is the primary interactive experience;
- both call the same `core` use cases and must produce identical behaviour.

The implementation should stay compact. Prefer explicit functions and small
data classes over frameworks, dependency-injection containers, databases, or a
general plugin system.

## 2. Required features

### 2.1 Root

- Initialise a user-selected ROOT.
- Resolve ROOT in this order: `--root`, `DOLCTL_ROOT`, parent search.
- An explicitly selected ROOT must already be initialised for every command
  except `init`.
- Keep every piece of launcher state below ROOT.

### 2.2 Instances

An instance is the user-facing name for the existing profile data model. For
on-disk compatibility it remains stored under `profiles/<name>/profile.toml`.

An instance contains:

- name;
- installed version id;
- ordered enabled mod ids;
- optional port override;
- optional browser-opening override.

Users can create, select, configure, list, and delete instances. `default`
always exists and cannot be deleted. Deleting the active non-default instance
selects `default`.

### 2.3 Versions

- Import a local zip or extracted directory.
- Discover and install releases from configured GitHub channels.
- List and remove installed versions.
- Detect the entry HTML at install time.
- Treat an installed version as immutable. Reinstalling the same id with
  `--force` creates a new install revision and invalidates dependent builds.

### 2.4 Mods

- Import a local zip or HTTP(S) URL.
- Require a readable `boot.json`; accept a single wrapper directory and
  flatten it during import.
- Read name, version, author, and description from `boot.json`.
- Store the original payload as `mods/<id>/<id>.mod.zip`.
- Enable, disable, and reorder mods per instance.
- Removing a mod also removes its id from every instance.

Complex dependency resolution and automatic compatibility solving are not in
scope. Load order is explicit and controlled by the user.

### 2.5 Build and launch

- Build `runtime/<instance>/merged` from the selected immutable version.
- Embed enabled mod zips in order into
  `window.modDataValueZipList` in the entry HTML.
- Cache builds using the version install revision plus ordered mod hashes.
- Build through a staging directory and publish only a complete result.
- Serve on loopback by default. `--allow-lan` is an explicit opt-in.
- Use port 8799 by default. An explicitly supplied port must either bind or
  fail; configured/default ports may fall forward to the next free port.
- Respect browser preference in the order command override, instance setting,
  global setting.

### 2.6 Diagnostics

One shared doctor use case reports:

- required directories and configuration readability;
- active/default instance validity;
- corrupt version, mod, or instance manifests;
- dangling instance-to-version or instance-to-mod references;
- stale/incomplete runtime data.

CLI and TUI render the same report.

## 3. Non-goals

- A Qt/Electron desktop clone of Prism Launcher.
- Embedded web browser or game save management.
- Mod dependency solving or remote mod marketplaces.
- Cloud sync, accounts, telemetry, or background update daemons.
- Multiple simultaneously managed servers inside one launcher process.
- Mod file-conflict analysis: ModLoader receives ordered archives, so dolctl
  reports load order rather than pretending to know runtime-level conflicts.

## 4. Root layout

```text
<ROOT>/
  .dolctl/
    config.toml
    state.toml
    cache/
      downloads/
      index/
    logs/
    staging/
  versions/
    <version_id>/
      .manifest.toml
      ... game files
  mods/
    <mod_id>/
      .mod.toml
      <mod_id>.mod.zip
  profiles/
    <instance_name>/
      profile.toml
  runtime/
    <instance_name>/
      merged/
      build_meta.json
```

The directory names and existing TOML fields remain backward compatible with
0.1.x. New schema fields are optional on read. Unknown or old build metadata
causes a clean rebuild rather than an in-place migration.

## 5. Safety and consistency rules

These rules are acceptance requirements, not implementation suggestions:

1. Instance, version, mod, and channel ids are exactly one safe path component.
   Reject absolute paths, separators, `.`/`..`, control characters, leading or
   trailing whitespace, and platform drive syntax.
2. Public remove/install APIs must prove their target is a direct child of the
   expected ROOT collection before mutating it.
3. TOML and JSON writes use a sibling temporary file followed by `os.replace`.
4. Version, mod, and runtime replacement stages complete content and metadata
   before replacing the previous directory. A failed force replacement keeps
   the previous installation usable.
5. Downloaded data is written to `.part` and renamed only after success.
6. Zip extraction rejects absolute paths and traversal, and enforces sensible
   member-count and uncompressed-size limits.
7. Expected external failures are translated to a `DolCtlError` subtype with a
   user-readable message; details remain available through exception chaining
   and logs.

## 6. Configuration formats

`.dolctl/config.toml`:

```toml
schema_version = 1
default_profile = "default"
default_port = 8799
open_browser = true
index_cache_ttl_seconds = 600

[channels.modloader]
provider = "github"
repo = "Lyoko-Jeremie/DoLModLoaderBuild"
asset_regex = "DoL-ModLoader-.*\\.zip"
```

`.dolctl/state.toml`:

```toml
schema_version = 1
active_profile = "default"
last_used_version = ""
```

`profiles/<name>/profile.toml`:

```toml
schema_version = 1
name = "default"
version_id = "vanilla-0.5.3"
mod_order = ["mod-a", "mod-b"]
# port = 8799
# open_browser = true
```

Version manifests retain the 0.1.x fields and add `schema_version` and
`revision`. Mod manifests retain their fields and add `schema_version` and
`sha256`.

## 7. CLI surface

Primary commands:

```text
dolctl init <dir>
dolctl where
dolctl doctor
dolctl tui

dolctl instance list
dolctl instance create <name> [--version <id>]
dolctl instance select <name>
dolctl instance show [<name>]
dolctl instance configure [<name>] [--version <id>] [--port <port>]
dolctl instance delete <name>
dolctl instance mod add|remove|reorder ...

dolctl version list
dolctl version install [<selector>] [--channel <name>]
                       [--file <zip> | --dir <directory>] [--as <id>] [--force]
dolctl version remote [--channel <name>] [--refresh]
dolctl version remove <id> [--force]

dolctl mod list
dolctl mod add <path-or-url> [--id <id>] [--force]
dolctl mod info <id>
dolctl mod remove <id>

dolctl channel list
dolctl channel add <name> (--preset <name> | --repo <owner/repo>)
dolctl channel remove <name>
dolctl channel preset

dolctl build [<instance>] [--clean]
dolctl run [<instance>] [--port <port>] [--no-browser] [--allow-lan]
dolctl serve [<instance>] [--port <port>] [--allow-lan]
```

The 0.1.x `profile`, top-level `install`, and `use` spellings may remain as
small compatibility aliases, but new documentation uses `instance` and
`version install`.

## 8. TUI experience

The TUI is instance-centred:

1. **Instances** — instance list, selected version, ordered mods, launch
   settings, Build/Launch/Stop.
2. **Versions** — installed versions plus remote/local installation.
3. **Mods** — local mod library and import/removal.
4. **Sources** — channel presets and custom GitHub sources.
5. **System** — ROOT information and doctor results.

Long operations run in worker threads. A shared operation wrapper handles busy
state, error presentation, progress, and the post-write data-change signal.
Screens never mutate disk directly and import only the public `core` facade and
DTOs.

## 9. Module boundaries

```text
dolctl/       Typer and Textual adapters only
core/         models, validation, use cases, build and launch orchestration
infra/        filesystem, TOML, zip, network, logging, browser adapters
providers/    concrete remote release providers
```

`core.launcher.Launcher` is the facade used by both frontends. Feature modules
remain independently testable. `dolctl.cli` imports Textual only inside the
`tui` command.

Cross-package imports are absolute; intra-package imports are relative.

## 10. Required verification

Every change set must pass:

```text
uv run --frozen pytest
uv run --frozen ruff check .
uv run --frozen mypy dolctl core infra providers
```

End-to-end acceptance covers:

1. init ROOT;
2. import a version and mod;
3. create/configure/select an instance;
4. build twice and observe a cache hit;
5. force-reinstall the same version id and observe a rebuilt runtime;
6. launch/serve the entry over loopback;
7. reject traversal/absolute ids without touching files outside ROOT;
8. inject failures during replacement and retain the previous installation;
9. mount and cycle through all TUI tabs;
10. import `dolctl.cli` without importing `textual`.
