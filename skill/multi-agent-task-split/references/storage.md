# Storage and materialized state

`.task/` is the **only repository-local control-plane root**. Source code, build outputs, logs, traces, decompiler output and other domain evidence stay outside it. Canonical records and bounded transient exchange files have separate directories.

## Canonical layout

Use this layout exactly; `bootstrap` is not a retained phase or a general archive:

```text
.task/
  semantic.yaml                 # one materialized current semantic view
  operator.yaml                 # mutable operator caps, not semantics
  config/                       # project-global machine policy
  provenance/                   # project/run identity
  directives/                   # immutable user directives
  payloads/                     # project-global content-addressed reuse
  operations/                   # script-only confirmed native release/ack steps
  m0_<milestone-slug>/          # long-lived milestone namespace
    packets/
    bindings/
    results/
    r0/
    reviews/
    requests/
    planner_rejections/
    planner_rejected_payloads/
  m1_<milestone-slug>/
    ...                         # same fixed typed directories
  tmp/
    m0_<milestone-slug>/
      goal.txt                 # sole Control-authored bootstrap input
      project.yaml              # temporary initial-planning inputs
      plan.yaml
      planning-request.yaml
      inventory.yaml
    runtime-view.yaml           # MATS-overwritten native view; never model-authored input
    planning-request.tsv        # fixed Control semantic form; finalized/removed by MATS
    deliveries/<packet-id>.yaml # exact worker-writable path
    side-requests/<dispatch-id>-<role>.tsv # fixed source-role semantic form
    completions/<dispatch-id>.yaml # MATS-only normalized worker_done staging
    instructions/<packet-id>.txt # only when inline text is unsuitable
```

`.task/tmp` is Control-managed staging, never semantic authority or provenance. A worker may write only its injected `tmp/deliveries/<packet-id>.yaml`; every other `.task` path is forbidden. Native-dependent MATS commands generate `runtime-view.yaml`; Control never checks, edits, supplies or refreshes it. `wait` alone writes normalized completion staging; `result <binding-id>` consumes it and removes delivery/completion files only after canonical import, automatic release of every one-shot in that native batch, and native acknowledgement. Tiny immutable `operations/` confirmations let retries skip already confirmed release/ack steps; they are never model inputs or a second lifecycle truth. A failed check/import/release/ack keeps the same fixed staging for idempotent retry. Do not create timestamped, `retry`, `v2`, `fix`, `final` or diagnostic copies in tmp.

Do not create path/SHA wrapper files or receipt wrappers. Commands accept documented IDs/paths and derive transaction data. Copy external instructions only to the exact tmp path above when a command requires a file.

Long-lived milestone files are never copied between `m.../` directories. The current `plan_id` selects the write namespace; internal refs may point to accepted evidence in older milestones. Normal flow rejects legacy top-level typed directories and invalid milestone refs with `TASK_MIGRATION_REQUIRED`. `mats migrate` only validates and returns `migration.md`; Control performs any complex move/ref rewrite manually from named issues.

Canonical filenames are mechanical keys, not prose: packet IDs are launcher-generated `p000001` indexes; bindings/results use native dispatch IDs; R0/reviews use candidate digest plus role; requests/rejections use content digests. Meaning lives in milestone/WP fields and YAML content. Control never invents packet filenames or encodes dates, retries, fixes or summaries in them.

## Milestone staging

Control writes one verbatim goal file under `.task/tmp` and runs `bin/mats bootstrap m0_<milestone-slug> --project-id <id> --goal-file <path>`. MATS creates the milestone staging paths, other bootstrap files, compact inventory, semantic seed and current Control receipt. There is no old bootstrap/init compatibility path. IDs are `m<number>` or `m<number>_<milestone-slug>`; the suffix names the milestone, not the project. Initial planning is `m0`; increment only for a real project-level milestone, never for review/repair/retry. A later Planner request pins the next `target_milestone_id`; Guard applies it mechanically after validation.

`init` accepts project/plan from `.task/tmp/m.../`. After initialization/application, `semantic.yaml` plus the long-lived milestone namespace are authoritative and staging may be removed. Planner outputs use their injected delivery path and canonical milestone `results/` import; never archive them in tmp.

## Current view vs history

`.task/semantic.yaml` is the **single materialized current semantic view**. It contains the current project model, current plan, pinned semantic/model-policy ref, current candidates, source refs, acceptances, invalidation fences, native Run provenance and the last applied planning anchor. It contains no native process lifecycle truth.

The model-policy ref is opaque identity/provenance. Never read or dereference `config/policy.yaml` or `policy_ref`; doctor and MATS scripts validate and consume them mechanically.

Temporary milestone project/plan files are not a second current-state authority or retained provenance. After initialization, normal roles read `semantic.yaml` or packet slices derived from it.

Runtime Planner calls return sparse patches. The semantic guard validates a patch, materializes the complete target project/plan, computes impact, then atomically replaces `.task/semantic.yaml`. No role replays historical Planner patches to reconstruct current state.

## Canonical logical paths

All semantic/internal refs use `/` POSIX separators even on Windows. Example: `m0_baseline/packets/p000017.yaml`, never `m0_baseline\\packets\\p000017.yaml`. Filesystem adapters convert host `Path.relative_to()` parts to a POSIX logical ref **before** schema/path validation. Windows drive letters, UNC roots and backslashes never enter an internal ref.

Absolute/native workspace paths may appear only in native receipts/runtime views where the schema explicitly represents a host filesystem location. They are not internal refs.

## Writes and locks

All admission and semantic commits share one OS mutex at `.task/coordinator.lock`, plus file fsync and atomic replace/create. POSIX uses `flock`; Windows uses `msvcrt.locking`. The OS releases it when the command exits or crashes. The persistent carrier file is not held-state and is never created, removed, inspected or maintained by a model. It is not a lease, heartbeat, worker resource or snapshot input. Native launch currently stays inside admission serialization because Orca exposes no MATS-compatible reservation/fencing receipt; do not shorten this critical section until that protocol exists and fault-injection tests cover unknown outcomes.

Candidate snapshot identity never uses host `stat()` permission bits: Windows Python and POSIX views differ for the same file. Git's binary worktree/index diffs own tracked content/mode identity; untracked files use canonical paths and SHA-256. `.task/` is excluded.

`.task/operator.yaml` is a separate mutable operator-control document. Cap changes do not change project/WP semantic digests.
