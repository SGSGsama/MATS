# Native Orca boundary

Orca is the only lifecycle authority for Runs, Tasks, Dispatches, terminals, worktrees, worker completion, cancellation, heartbeat and waits. This Skill does not mirror those states or infer native liveness.

## Mechanical bridge

Normal managed launch goes only through `bin/mats dispatch`. Before any native mutation the bridge performs a read-only `task-list` probe:

- already bound to the expected semantic `run_id` -> continue;
- native returns `run_required` -> mechanically `run-use --id <expected>` and verify by another read-only `task-list`;
- bound to a different Run -> fail closed; do not silently rebind/hijack it;
- any other native error -> stop and inspect the version-matched Orca guide.

For Control-classified cybersecurity dispatches, `-cyber` mechanically replaces a Sol primary with `gpt-daybreak-blue-latest` at the same effort. The bridge may issue one Sol fallback launch only when the primary receipt explicitly identifies the model as unavailable. The normalized receipt records that attestation; unrelated launch failures are returned without fallback.

If a bound dispatch is natively confirmed `failed`, retry only with `bin/mats dispatch --retry-packet <packets/...yaml> --retry-sha256 <digest>`. The launcher loads the existing digest-pinned packet, refreshes native state, reuses its placement/access and derives its role/WP/cyber fields before creating a fresh native Task. It rejects a packet with no prior binding, any prior outcome other than `failed`, and every fresh semantic or continuation override. This is transport/lifecycle recovery, not a new bootstrap or Planner occasion.

Only after that check does the bridge create the Task and start the worker. Fresh child launches must return the exact resolved `launch.effective`; missing/null/mismatched binding or unattested fallback is semantic launch failure, not permission to continue with a default model.

The bridge uses subprocess argument arrays, never shell command strings, so Windows quoting/spaces do not change Task specs.

## Event-driven completion

Every supervised dispatch is followed by `bin/mats wait --control` or the exact Owner `--actor-packet` command injected at launch. Owner/leaf waits remain a single native wait for `worker_done,escalation,question`. Control wait may be called immediately: it first probes Run mail without blocking and derives the relevant active Dispatch set from a fresh normalized view. If both are empty it returns the current deterministic `advance` state immediately. Otherwise it watches Run mail plus every active bound Dispatch, including the newest current same-session context-only Owner continuation. Queued lifecycle mail always wins. A pure question/escalation batch is acknowledged immediately after it is captured for the Control response; a batch containing `worker_done` is never acknowledged before all staged imports succeed. Exact successful completion of that context continuation with a confirming empty mail peek becomes `CONTEXT_TURN_COMPLETED_WITHOUT_EVENT`, and MATS sends one compact continuation to the same Codex session. Settlement of any other active Dispatch without an importable delivery returns `BLOCKED/LIFECYCLE_DELIVERY_MISSING` immediately; `failed`, `stopped`, `abandoned` and `cancelled` are never auto-resumed. If another waiter imported the delivery during the race, MATS returns current `advance` state instead. It never uses TUI-idle/title/composer state, resumes a fresh/replaced/old dispatch, asks the user to notify Control, or waits after native work has ended. The outer 20-minute timeout remains one checkpoint only for a real blocking wait. For `worker_done`, MATS verifies run/task/dispatch/outcome against its binding, derives the only importable draft from that binding and stages a fixed script-owned completion. Top-level `next_operation: advance` is the normal path; per-binding `result` operations remain exact recovery. The batch path imports every completion, releases every one-shot R1/R2/Planner/Luna/Synthesis dispatch, records each confirmed release, then records one FIFO acknowledgement and cleans tmp. Owner sessions are never released here. Failure preserves staging and already-confirmed operations for idempotent continuation. Orca `reportPath` remains optional display metadata: MATS never opens it or uses it as an import selector. Control never locates/authors receipts or manually releases one-shots. Verified checkpoints/completions have no mandatory reread; other events list exact refresh paths. Timeout/checkpoint never means failed, stopped, stale or retryable. Status inspection is diagnosis/recovery only, not a model-driven completion-poll loop.

## Terminal delivery

Free-form terminal messages use `bin/mats native-send`; they are not lifecycle transitions. Fresh launches use native `worker-start`. A retained Owner resolves the current terminal from the exact bound Codex session ID, creates a plain same-terminal context Dispatch without Orca prompt injection, then sends the compact Task spec plus exact lifecycle route once and follows it with one pure Enter. Active `steer` uses the same session proof and direct prompt+Enter wake-up; it never leaves an adjustment only in an unread orchestration inbox. These paths do not require `agentIdentity`, `worker-start --terminal`, agent recognition or `dispatch --inject`. A structured `ok: true` receipt is authoritative even if a Windows wrapper exits nonzero.

## Freshness and identity

MATS captures normalized runtime views internally from `status`, `worker-list` and the exact repository worktree inventory; it starts Orca at most once if status is not ready. Control never creates/checks/passes `runtime-view.yaml`, guesses permission context, or runs those raw commands in a normal transition. Bound `dispatchStatus` is lifecycle-authoritative; worker fields are compatibility fallback. A field written into YAML never authenticates itself.

The first Owner session stays retained through its same-WP review/repair loop; `worker_done` ends one dispatch, not that terminal/session. The receipt's Codex session ID is the sole durable Owner index. MATS enumerates the exact workspace and requires one connected/writable terminal with that session; handle, old dispatch, PTY, `agentIdentity`, external/user-takeover/retained labels and runtime epoch are replaceable metadata, never identity. An absent session permits fresh/full; an unavailable, duplicate, misplaced or non-writable session stops with its stable reason code.

For a proved retained Owner, MATS creates a Task whose spec is only the verbatim instruction, content-addressed semantic delta, short role/Control recap, delivery gate and supervising Control session, then context-dispatches it to the session-resolved handle. It passes no model/effort and never repeats fresh init/full Role Contract/full packet. MATS sends that spec with the new lifecycle IDs and one pure Enter; `worker-show` must attest the same Run/task/dispatch/session/worktree before binding.

Before creating another continuation, MATS reconciles its same-Run/WP/Control-session ready and dispatched Tasks against current immutable packet ID+digest. It fences only a stale idle `unsupervised/context_only` Dispatch (the pre-existing Owner terminal is retained), settles superseded ready retries, and reuses the newest exact ready Task. An exact context-only Dispatch receives its spec once; an already-executing exact Dispatch is bound without duplicate input. Ambiguous or possibly executing stale work stops. Only an explicit user migration instruction permits `mats migrate` and the returned manual.

One writer per worktree remains the admission rule. Read-only work may share only a true immutable snapshot or otherwise non-racing view. Native worktree/session identity must be real host identity, not a guessed path label.

## When to load Orca's full guide

Do **not** load `orca skills get orchestration` during activation or child execution; the injected preamble and MATS public commands are sufficient. Control first loads this file and uses exact `mats <command> -h`. `orca-cli` is a last syntax fallback only after long-task compaction removed necessary CLI syntax and exact help failed. A still-unreconciled public bridge error is reported as a tool bug, not repaired by reading private scripts.
