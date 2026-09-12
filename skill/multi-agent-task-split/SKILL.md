---
name: multi-agent-task-split
description: Managed task decomposition and Orca role dispatch.
---

# MATS v1.1.0

## Activate

Control: Luna/max.

1. Read all of `SKILL.md`.
2. Read `references/roles/control.md`; require all seven labels through `Refresh:`.
3. Read `references/workflow.md` through `MATS_WORKFLOW_EOF`.
4. Read `references/routing.md` through `MATS_ROUTING_EOF`.
5. Run `bin/mats activate --repo <repo>` once (Windows: `bin\mats.cmd activate --repo <repo>`).
6. Set `LOAD_COMPLETE` only if every read reached its marker and doctor succeeded.

Before `LOAD_COMPLETE`, no classify/decompose/dispatch. Missing marker/activation failure -> STOP. Never enumerate the Skill tree/`.venv`.

`config/policy.yaml` is script-private.

Load `storage.md` before the first state/path operation. Load `native-boundary.md` only for native lifecycle/identity/recovery/CLI anomalies; never preload it/Orca. `TASK_MIGRATION_REQUIRED` -> STOP/report. Only explicit user migration direction permits read-only `mats migrate` and its returned `migration.md`; normal flow has no legacy branch.

Read once; reload only on `Refresh:`; never inventory `.task` or substitute summaries for named authorities.

## CLI boundary

`bin/mats`/`bin\mats.cmd` enter isolated `.venv`. `MATS_NOT_INSTALLED` repair is outside model authority. Never call Python or read `scripts/*.py`. Use `bin/mats <command> -h` only for missing syntax; recovery commands never replace `advance`.

Missing/contradictory public recovery or required script/Guard edits -> STOP and report the tool bug; never improvise or ask the user to do MATS mechanics.

## Dispatch / wait

`dispatch` launches children and verifies model/effort/runtime/workspace/access/receipts. Native-failure retry uses the same digest-pinned packet.

After bootstrap/`wait`, use `mats advance`; `--resume-owner` consumes a Control resume without forwarding it. Continue/retry/progress/status/Skill/tool/lifecycle/session input targets Control, never steer. Answer from user/control state/verified summaries directly; only a pure domain question needing new evidence uses `mats query`, once. Return `OWNER_ANSWER_READY`, never re-query. Product/evidence work uses steer/continuation; terminal prose never replaces `deliver` + `worker_done`. `advance` stops after one dispatch or at `WAIT`/`READY`/`NEEDS_DECISION`/`BLOCKED`/`DONE`. Interpret only `NEEDS_DECISION`, never error prose; `--dry-run` is nonmutating.

Keep first Owner per WP while work remains; `worker_done` never releases it and `failed` is not a checkpoint. Continue by Codex session ID: rebind, reconcile orphan Task/Dispatch, send one instruction+delta+role/Control recap and Enter; never resend init. Recognition/handle labels never release/fresh. Missing session gets full context.

Models fill generated TSV cells/paths; MATS creates YAML/IDs/refs/versions/hashes/snapshots. Injected `deliver <packet-id>` gates `worker_done`; `evidence` handles bulk files. Planner uses `planning-request-form`; repair is prefilled.

Preambles/routes contain lifecycle CLI. Children never load `orchestration`; use `orca-cli` only after two compactions and failed exact help.

MATS controls roles/scope/reviews; `scope.refs` advises reads and `specialty` is descriptive. Domain skills cannot change authority or acceptance.

Control wait: no active => `advance`; else mail/settlement. Only successful context resumes; missing delivery blocks; mail wins. Worker wait: mail-only. Follow `advance`; 20m=checkpoint.

## State and semantics

`.task/` is the control root. Control manages `.task/tmp`; workers write only delivery or an injected query-answer path. Control writes one tmp goal and runs `bootstrap`; Run/milestone files are mechanical. Long-lived records use `m<number>_<milestone-slug>`; packet IDs are indexes. `bootstrap` is not retained. Internal refs use POSIX `/`.

Orca owns native lifecycle; MATS owns roles, packets, evidence, routing and acceptance. `worker_done` is not acceptance. The loaded workflow/routing tables are the complete transition and delegation rules.
