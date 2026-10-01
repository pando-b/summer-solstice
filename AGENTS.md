# Agent rules for this repo

This is the **public** Summer Solstice plugin: a generic product factory. It
must never contain live intel.

- **No live intel here.** No product names, slugs, or domains of products in
  flight, no competitor names in live use, no records, no event files, no
  workspace config, no account IDs, and no secrets. Tests and fixtures use
  synthetic data only, and every file under `cli/tests/fixtures/` carries the
  marker `solstice-fixture: synthetic`. Build secret-shaped test strings at
  runtime.
- **Knowledge work about live products runs from the private workspace
  checkout,** not this one. `ce-plan`, `ce-compound`, and similar work about a
  real product write into the workspace's own `docs_root`. In this checkout,
  compound-engineering writes to `.ce-artifacts/`, which is gitignored and
  must stay untracked.
- **Never run `git push --no-verify` on this repo.** The pre-push hook in
  `.githooks/pre-push` scans every pushed commit (contents, paths, and
  messages) against the private denylist and secret patterns, and it fails
  closed. If it blocks a push, remove the leak from the commits; do not
  bypass it.
- **Confirm the hook is armed** with `solstice doctor` (the `pre-push hook`
  line must be `ok`). Arm it with
  `solstice hooks install <this checkout> --workspace <private workspace>`.
- v1 skills under `skills/` stay untouched until they are removed in the v2
  release.

Run the CLI tests with `cd cli && uv run pytest -q`.
