# Manual `.task` migration (last resort)

Load this file only after the user explicitly directs migration and `mats migrate --repo <repo>` returns `valid: false`. A normal `TASK_MIGRATION_REQUIRED` is only a STOP/report signal; it does not authorize running the validator or reading this guide. Migration is an explicit operator mode, not a normal workflow branch. `mats migrate` is read-only: it never moves files, rewrites refs, removes locks or changes Orca lifecycle state.

## Invariants

- Back up the exact `.task` directory before changing it. Do not modify product files or infer a product-directory layout.
- Work from the validator's stable issue list. Inspect only named paths and exact referenced records; do not inventory unrelated project directories.
- Preserve every canonical artifact byte-for-byte unless a reference must be rewritten. An internal ref is exactly `path` plus `sha256`; after an intentional move, update every referencing record with the new POSIX `/` path and the canonical YAML digest.
- Never bulk-move or bulk-rewrite an arbitrary tree. Never overwrite, merge or discard conflicting artifacts. Stop and report ambiguity.
- Milestone IDs are `m<number>` or `m<number>_<milestone-slug>`. Long-lived `packets`, `bindings`, `results`, `r0`, `reviews`, `requests`, `planner_rejections` and `planner_rejected_payloads` live below the correct milestone. Packet names are `pNNNNNN.yaml`.
- `tmp/` is staging, `archive/` is non-authoritative operator history, and neither may satisfy a canonical internal ref.

## Procedure

1. Run `mats migrate --repo <repo>` and save the report outside `.task` if a record is needed.
2. Back up `.task`. Determine the correct milestone for each reported legacy artifact from `semantic.yaml`, packet fields and exact internal refs. Project complexity is the reason this decision is manual.
3. Reconcile native state only when the report or `TASK_MIGRATION_REQUIRED` names an exact legacy dispatch. Use public Orca `worker-show`/terminal inspection for that exact Run, task, dispatch, session and worktree. A composer preview or `user-takeover` label alone is not lifecycle truth.
4. `unsupervised/context_only` alone is a current valid existing-terminal dispatch and never a migration trigger. Reconcile only an explicitly named incompatible legacy dispatch; if active, ambiguous or unverifiable, make no lifecycle change and report it.
5. Move only the individually verified artifacts into their milestone typed directories. Rewrite all affected internal refs and hashes together. Old top-level material with no canonical incoming refs may be moved to `.task/archive/pre-v17.7/`; never use the archive to conceal unresolved refs.
6. Remove `admission.lock` or `semantic.lock` only after confirming they are obsolete carrier files rather than project data. The current `coordinator.lock` is OS-released and is never manually maintained.
7. Rerun `mats migrate`. Repeat only for its remaining named issues. When it returns `valid: true`, leave migration mode and run `mats activate`.

During migration only, Control may author the necessary transaction-path/ref corrections and use the named public Orca lifecycle command. This exception ends immediately when validation passes. The ordinary workflow still forbids hand-built transaction files, raw lifecycle improvisation and legacy compatibility paths.
