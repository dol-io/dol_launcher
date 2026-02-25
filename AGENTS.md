# Repository Guidelines

This repository currently contains the product specification in `requirement.md`. Treat it as the source of truth for behavior, acceptance checks, and module boundaries; update it if you intentionally diverge.

## Project Structure & Module Organization
Expected layout:
- `dolctl/` — Python package containing **only** CLI entry points (`cli.py`, `__init__.py`)
- `core/` — top-level package: business logic (`build.py`, `mods.py`, `models.py`, `profiles.py`, `root.py`, `run.py`, `serve.py`, `versions.py`)
- `infra/` — top-level package: infrastructure helpers (`fs.py`, `log.py`, `net.py`, `open.py`, `toml.py`, `zip.py`)
- `providers/` — top-level package: remote index implementations (`github.py`)

Keep `dolctl/` thin (CLI only). Business logic lives in `core/`, helpers in `infra/`, remote index logic in `providers/`. Cross-package imports are absolute (`from core.models import …`, `from infra.fs import …`). Intra-package imports stay relative (`from .root import …`). Runtime data must live under a user-selected ROOT (e.g., `~/Games/DoL/`) with `.dolctl/`, `versions/`, `mods/`, `profiles/`, and `runtime/` subfolders.

## Build, Test, and Development Commands
Use Python 3.11 with `uv` (see `pyproject.toml`). Typical commands:
- `uv sync` to create the environment
- `uv run dolctl init <dir>` to create the root layout
- `uv run dolctl install --file <zip> --as <id>` to add a version
- `uv run dolctl build --profile <name>` to merge mods
- `uv run dolctl run --port 8799` to serve locally

## Coding Style & Naming Conventions
Use 4-space indentation and PEP 8–style naming (`snake_case` functions, `PascalCase` classes). Match module naming patterns from the spec (`core_versions.py`, `infra_zip.py`, `providers_github.py`). Do not write across layers directly; interact through core interfaces.

## Testing Guidelines
Tests are not committed yet. If you add them, place tests under `tests/` and name files `test_*.py`, then run `uv run pytest`. Until then, document manual verification steps in your PR (e.g., `dolctl init`, `dolctl build`, `dolctl run`).

## Commit & Pull Request Guidelines
Git history currently contains only “Initial commit”, so no convention is established. Use concise, imperative subjects (e.g., “Add profile model”) and keep commits scoped. PRs should include a short summary, linked issues (if any), and the commands you ran. If behavior changes, update `requirement.md`.
