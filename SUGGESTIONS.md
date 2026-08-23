# Open review notes

> Updated for the 0.2 instance-first rewrite on 2026-08-23. `intro.md` remains
> the product source of truth. These are deliberately deferred improvements,
> not missing acceptance requirements.

## 1. Large Mod bundles

The compatible ModLoader path embeds each enabled zip as base64 in the entry
HTML. This is simple and reliable, but large mod sets inflate the document and
increase browser parse cost. A future release may emit a separate generated
JavaScript bundle if compatibility testing confirms that approach.

## 2. Native file selection in the TUI

Local version and Mod imports currently accept typed paths. A file picker would
be friendlier, but it should remain a front-end concern and must not add desktop
framework dependencies to the core launcher.

## 3. Additional release providers

The provider boundary is intentionally small, but only GitHub Releases is
implemented. Add another provider only when there is a concrete upstream in
use; do not introduce a dynamic plugin registry pre-emptively. In particular,
official vanilla builds currently use Blogspot/Pixeldrain rather than GitHub
Releases, so they remain a local import until a stable index API is available.

## 4. Build-storage optimisation

Each instance currently owns a complete runtime copy. Hard-linking or a
content-addressed store could save disk space, but would make replacement and
cross-filesystem behaviour more complex. Prefer the current predictable model
until real installations show that storage is the limiting problem.
