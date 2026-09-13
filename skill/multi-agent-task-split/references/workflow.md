# Managed workflow

## Activation and CLI discovery

Complete the ordered activation sequence in `SKILL.md`. `mats activate` validates the runtime and refreshes the current Control receipt when semantic state exists; it does not start Orca. Do not classify, decompose, inspect other managed state or dispatch before `LOAD_COMPLETE`.

`config/policy.yaml` is not a Control input. Never open it. Doctor, dispatch and Guard own its validation and interpretation.

The executable interface is `bin/mats` on POSIX/Git Bash and `bin\mats.cmd` on Windows. Loaded references define the normal flow. If an exact flag is absent, run `bin/mats <command> -h`; do not open `scripts/*.py`. MATS commands are not direct Orca CLI use. Never load `orchestration` or fetch its full guide. Load `native-boundary.md` only after a native lifecycle/identity/recovery/CLI anomaly; `orca-cli` is the last syntax fallback only after long-task compaction and failed exact help.

## Control progression

Control owns bootstrap and genuinely semantic user-input classification. Once semantic state exists, `mats advance --repo <repo>` is the normal deterministic progression command. It uses canonical MATS state plus a fresh normalized native view and may import staged completions, run R0, route R1/R2, return exact `fix_local` or Synthesis evidence to the retained Owner, turn a source-authored `plan_conflict` into a neutral Planner request, apply a valid Planner result, release an Owner only when Guard proves it is the final blocker, and retry guarded acceptance. These transitions share Guard/routing code; Control never reconstructs them from documents or matches `detail` text.

One invocation performs at most one new worker dispatch and at most `--max-steps` local transitions (default 16; range 1..64). `--dry-run` selects a next action without creating a packet, task, delivery or semantic transition. Never wrap `advance` in an unbounded shell loop.

The first Owner of each WP requires an explicit Control classification: rerun the returned choice with `-cyber` or `--non-cyber`. Omission returns `NEEDS_DECISION/CYBER_CLASSIFICATION_REQUIRED`; it never silently means non-cyber. Candidate-derived R1/R2/Synthesis/repair inherits the original classification without asking again.

| `advance` status | Control action |
|---|---|
| `WAIT` | Run `wait --control`; it blocks only while a relevant Dispatch is active, advances verified mail, and mechanically continues only a successful current context turn that emitted no mail |
| `READY` | The local step limit yielded; run `advance` again |
| `NEEDS_DECISION` | Stop automatic progression. Interpret only the returned question/source/constraints; choose only from prior explicit user/plan authority or ask once when required |
| `BLOCKED` | Preserve `reason_code`, `detail`, attempted action and trace; use only a returned/documented recovery, otherwise report a tool/protocol block |
| `DONE` | Report completion from accepted artifacts |

Stable `reason_code` and structured `next_operation` are machine interfaces; human-readable `detail` is diagnostic only. Explicit `result`, `r0`, review dispatch, Owner release and accept commands remain single-step recovery/debug paths, not a parallel Control state machine. Missing/ambiguous state, unknown native outcome or contradictory rules stop deterministically; Control never chooses a plausible recovery.

Before semantic state exists, write the user goal verbatim to one file under `.task/tmp`, run `bootstrap`, dispatch its returned Planner request, then use `wait`/`advance`. Run ID, seed files, inventory and Control attachment are derived mechanically.

Classify the addressed role before routing any later user input:

| User input | Target and action |
|---|---|
| Continue/resume/retry, check progress/status, Skill/tool/lifecycle/session diagnosis, or a request for Control to keep coordinating | Control. Answer from MATS/native state or run the applicable `advance`; never put this text in `steer`, `dispatch --instructions` or a child prompt. After `OWNER_RESULT_NOT_CANDIDATE`, explicit user authority to continue maps to `advance --resume-owner` |
| Question answerable from user text, control state or an already verified semantic summary | Control answers directly; no read/search, worker message or dispatch |
| One bounded domain question requiring new evidence from a retained Owner | Owner query. Pass it unchanged through `mats query`; do not use `steer`/continuation or repeat it |
| A concrete product change, test, evidence/log interpretation, domain constraint, or explicit instruction to Owner/worker | Owner. While its dispatch is active relay the exact text with `steer`; while inactive use the returned continuation route. Do not expand it |
| Role target is ambiguous and choosing a target changes work | Control. Ask once; do not send speculatively |

For a test request or evidence/log addition addressed to an inactive retained Owner, pass it unchanged with `dispatch --continue-owner`; use `steer` only while its current dispatch is active.

Control answers without worker I/O when user text, control state or an already verified semantic summary is sufficient; it never opens new product/domain material to make that answer. `mats query` is the low-I/O path only when an answer-only question needs new evidence. It reuses the retained Research/Engineering Codex session without a packet, fresh init, candidate, delivery form or new role decision. The Owner writes one concise reply to the fixed tmp path and runs the injected `mats answer` once; that command sends a correlated non-completing status event. `wait --control` verifies it, acknowledges it, deletes both tmp files and returns `OWNER_ANSWER_READY`. Control returns that exact answer once and does not advance, continue, steer or query again for it. A normal continuation is never answer-only: terminal prose is not delivery and it must pass `deliver` plus one `worker_done`.

Neither Owner route permits Control product inspection or domain judgment; preserve every external-mutation approval condition, then return to `wait`/`advance`. A truly ambiguous WP/commitment/authority decision remains Control work under the routing rules below.

Control never performs Owner, Synthesis, Reviewer or Planner reasoning or executes domain commands. It reads current MATS semantic/control artifacts for transitions, but never searches/opens product source, binaries, raw domain logs/evidence or worker transcripts to diagnose work. The Script authority is limited to named MATS CLI operations defined in `routing.md`; work size, cost and read-only status never widen it. A domain skill supplies methods inside an already selected packet; it never selects a state-machine transition.

Questions are not Planner occasions. Route tests, evidence/log additions, behavior corrections and reversible in-scope details to the retained Owner without prior domain investigation. Compare directives only with the materialized project/plan; product impact, protocol/API/architecture vocabulary or Control's own implementation inference never proves a Planner trigger. Absent an explicit conflict, route the text unchanged: the Owner receives the directive and returns `plan_conflict` if its contract must change. A valid Planner request preserves source text and must write a neutral decision question; Control adds only required structure, cited state facts and explicit authority limits. It never turns an ambiguous term into an architecture, protocol/frame format, compatibility/fallback policy, algorithm, test design or acceptance rule. Read paths are advisory and need no Control grant; cited current inputs are pinned at delivery. If a Planner was mistakenly opened, close its exchange without applying the proposal. Resolve MATS schema/ref/hash/snapshot/runtime/routing/retry/session mechanics locally through public commands. Ask the user once only for an unavailable goal/authority decision or irreversible/external mutation approval.

`OWNER_RESULT_NOT_CANDIDATE` stops automation. The Owner's own `decision_requested`, `unresolved` or "not this round" statement is not authority for another turn and cannot become a Control-authored prompt. A user Control-level "continue/resume" authorizes `advance --resume-owner`; MATS cites the exact source result and does not forward the user's orchestration text. A new Owner-directed product instruction follows the route table above. Otherwise surface the decision. While local in-scope work remains possible, Owners keep working and never use `failed`/`worker_done` as a checkpoint. Loading a required Skill or announcing an approach is not progress completion: the Owner acts in that same turn and cannot stop with intent, diagnosis or next-step prose.

For a valid non-bootstrap Planner occasion, run `planning-request-form`, fill only its semantic TSV cells, then run its returned `planning-request` operation and dispatch the returned immutable request path. Directive `raw_text` stays verbatim and the question stays neutral. MATS stores the directives and generates request schema, refs, hashes and filenames; Control never authors directive/planning-request YAML or path/hash wrappers. `planner-repair` remains fully generated from the immutable rejection and requires no form editing by Control.

Normal native preparation is one MATS command. Never test for `.task/tmp/runtime-view.yaml`, ask the host to create it, call raw `orca open/status`, inspect processes, run legacy `control`, or load the full Orca guide before `dispatch`, `accept` or `apply-plan`. `activate` already refreshes the current Control session. Native-dependent commands start Orca at most once when needed, resolve workspace/access, capture a compact view and run Guard internally. The fixed runtime-view file is script output. A returned native error is the only anomaly input.

## Control path invariant

At `LOAD_COMPLETE`, bind the exact host workspace repository and pass it with `--repo` on every MATS command. That repository is the only Control path root; shell CWD, a previously visited directory and host temp never grant write authority. Every Control-created log, capture or redirect uses one fixed reused path under that repository's `.task/tmp`; Control writes no external path.

The same repository bounds reads. Other Runs, terminals and workspaces in native inventory are opaque; never enumerate, open, hash or Git-inspect them or use one as a substitute. No Git HEAD -> STOP for user-authorized baseline initialization or path correction; never initialize, search or switch by inference.

Before every file write, classify the target as canonical Guard-owned state or Control-managed staging. Guard writes typed long-lived records under the current `m..._<milestone>/`; Control never writes those files itself. Staging goes only to `.task/tmp`; never put drafts, receipts, instructions, diagnostics or ref wrappers in canonical directories. Reuse the fixed tmp filename; do not create timestamped, `retry`, `v2`, `fix` or `final` variants. Workers write only the injected delivery path. Successful Guard import precedes Control cleanup; failed validation keeps the same path and session.

## Bootstrap and Planner recovery

For initial staging, write the user goal verbatim to one file under `.task/tmp`, then run `bootstrap m0_<milestone-slug> --project-id <id> --goal-file <path>`. It derives the bound Orca Run and generates the milestone paths, seed project/empty plan, compact Git inventory, bootstrap request, state and current Control receipt. Control never writes those YAML contracts. No old bootstrap/init path exists. A milestone ID names the milestone, never the project. A true later milestone uses a Planner request with `target_milestone_id=m<current+1>_<milestone-slug>`; Guard changes identity/namespace after validation. Repository inventory is mechanical; Planner decides greenfield versus adoption.

`activate` refreshes Control on every newly activated Control session. `bootstrap` also attaches it. Old init/control/bootstrap-init commands are removed; `migrate` validates old state but never executes it.

A successful bootstrap apply consumes the initial bootstrap occasion. A rejected proposal does not consume it. Never archive, reset or reinitialize `.task` to create another bootstrap.

Two failures have distinct transitions:

| Failure evidence | Required command path | Prohibited action |
|---|---|---|
| A bound native Planner dispatch is present and every binding for that packet is natively `failed` | `dispatch --retry-packet <packets/...yaml> --retry-sha256 <digest>`; the launcher refreshes runtime state and starts a fresh native Task from the exact stored packet | New packet, new name/operation/request/instructions, continuation, or `-cyber` override |
| Planner output was imported but rejected by schema/semantic Guard | `planner-repair <planner_rejection_path> --sha256 <digest>`, then dispatch the mechanically generated fresh repair request | Reusing the rejected packet, hand-editing repair fields, changing the base/occasion, or resetting state |

Packet retry requires at least one prior immutable binding. Unknown, running, succeeded or missing outcomes are not failed and block retry. The stored packet supplies role, WP and cyber classification; Control supplies no replacement semantics.

Runtime Planner output is `project_patch + plan_patch`. Roles read materialized current state and slices, never Planner patch history. When an Engineering boundary itself is a material architecture decision, Planner may attach `interface_specs` with exact declarations and invariants/lifecycle/compatibility/validation obligations. This is a decision artifact, not product code: routine local design and function bodies remain Engineering work. `required` is exact or yields `plan_conflict`; `advisory` may be adapted with evidence without changing commitments or exit conditions.

## Dispatch contract

Every managed child starts through `dispatch`. Control supplies semantic operation plus packet inputs, never packet name/model/effort/runtime-view/workspace-key/access. The launcher generates the next global `p000001`-style packet ID, derives role/model/effort/placement access, refreshes native state, applies Control's cyber bit, performs admission, creates a Task and verifies binding/workspace identity. A fresh role/session uses `worker-start` and receives the complete Role Contract and packet. A viable same-WP continuation uses the bound Codex session ID as its sole durable index, reacquires the current handle, creates a plain context Dispatch without agent recognition/injection, sends the compact Task spec plus exact lifecycle route once, then sends one pure Enter. MATS never repeats fresh init/full contract/full packet. Only an absent session gets a fresh process and full context.

Every worker directly requests any required but unavailable remote evidence through the native preamble, naming the exact missing evidence. It does not guess/fabricate evidence or misclassify that absence as a MATS/Guard failure. Evidence that is not required does not create a question.

Research may add structured `recovered_specs` for binary-derived facts. It writes semantic subject/evidence paths, locators, facts, validation and honest confidence; finalization pins subject/evidence identity. Downstream packets project those facts and paths without hashes. Engineering cannot author recovered discovery, and Planner never transcribes it merely to pass it downstream.

Every dispatch starts with a launcher-generated UTF-8 TSV semantic form at `.task/tmp/deliveries/<packet-id>.yaml`; that fixed path is replaced by canonical YAML only after finalization. The role fills semantic cells/paths only. Owner `status` is `candidate|blocked|failed|plan_conflict`, never native `succeeded`; `candidate` asserts every WP exit condition. Ordinary evidence, including GNU `.sha256` lists, uses an `evidence` row. `evidence_manifest` is only a bulk hint: MATS recursively expands content marked as its own YAML bundle and otherwise safely pins the named file as ordinary evidence. `memo_source` cites prior `.task` results/reviews; a legacy internal path placed in `memo_evidence` is mechanically reclassified. The injected `deliver <packet-id>` derives the packet digest, fixed form path and bound workspace, generates every transaction field/ref/hash/version/snapshot, atomically writes canonical YAML, and validates context. It never imports state. Only exit 0 plus `valid: true` permits delivery. Correct semantic cells and recheck in-session. Contradictory validation or missing recovery is reported once as a tool bug. No old packet finalizer is executed. `result <binding-id>` imports, releases one-shot roles, acknowledges and removes tmp; it never releases an Owner.

The current workspace snapshot and every other transaction field are intentionally absent from model inputs. Their absence never means `blocked` or `failed`: the role completes semantic work and runs its injected finalizer, which computes and authoritatively replaces those fields from the assigned workspace. Historical candidates are not a substitute and no role reconstructs the snapshot. Before finalization the role stops its background processes and closes/flushes owned handles; after finalization it makes no workspace/evidence mutation.

| Interaction | Role-authored content | MATS-generated content |
|---|---|---|
| Control -> Planner | reason, neutral question, verbatim directives, affected WP IDs and source paths | directive/request YAML, filenames, schema and internal refs/hashes |
| Owner -> Control | status, concise summary, evidence paths, unresolved/impact/tags, claims/unknowns, side dispositions | canonical contract, schema, candidate snapshot, path hashes/versions, side binding refs, memo defaults |
| R1/R2 -> Control | outcome, concise findings, evidence paths, claims/unknowns | schema, exact candidate target, hashes/versions |
| Luna/Synthesis -> Owner | status, bounded conclusion, evidence paths, unknowns, coverage/actions | schema, evidence hashes/versions, empty coverage exclusions |
| Planner -> Control | bootstrap semantic target or runtime sparse patch, rationale, and optional architecture-bearing Engineering interface declarations/obligations | canonical contract, mode, schema, base/target versions and pinned project/plan/milestone identities/refs |
| Owner/R1 -> side role | question/class/findings/attempts/decision/verification plan | schema and evidence identity; R1 may reuse exact candidate evidence without copying it |
| Native Orca -> Control | none | launch/completion identities and effective binding receipts |

For more than a few delivery evidence files, the Owner runs its injected `evidence <packet-id> <output> <inputs...>`. MATS derives packet digest/workspace and creates one deterministic manifest within Owner scope; Guard recursively checks it. Candidate/review packets project paths while keeping hashes, versions, receipts and snapshot manifests out of model context.

Normal completion returns top-level `next_operation: advance`; `ready_results[].next_operation` retains the exact `result <binding-id>` recovery path. `advance` imports every completion in the batch. Only after all are canonical does it release **every** one-shot R1/R2/Planner/Luna/Synthesis dispatch in that batch, persist each confirmed release, persist the batch acknowledgement, and clean tmp; Owner sessions are never one-shot. Release/ack failure preserves the same staging and exact idempotent recovery without repeating confirmed mutations. Control never enumerates terminals, calls raw `worker-release`, locates receipts or hand-builds refs/hashes. `result` consumes only script-staged completion state; explicit files are not accepted.

Call-specific instructions remain subordinate to role, packet, scope, review and acceptance. Owners can request bounded read-only Luna Aux only through a source-authored side request satisfying the delegation table. If native depth blocks Owner placement, Control submits the unchanged request through the same launcher.

For cybersecurity work—including vulnerability analysis, reverse engineering and the other positive cases in `routing.md`—Control passes `-cyber`. A Sol-bound role then uses `gpt-daybreak-blue-latest` at the same effort. Only an explicit primary-model-unavailable receipt causes one automatic Sol fallback.

## Candidate and review chain

`worker_done` only authorizes result import. The Owner produces a content-pinned candidate. The fixed chain is candidate -> R0 -> fresh R1 -> conditionally required R2 -> Owner release -> guarded accept. R1/R2 use `read_snapshot` and coexist with the retained writer. Only accepted dependencies unlock downstream WPs.

Keep the first Research/Engineering Owner session through candidate, blocked/failed correction, reviews, Synthesis and local repair; `worker_done`, result import and reviewer dispatch are not release conditions. Use the returned continuation route while inactive and `steer` only for Owner-directed input while active. `steer` resolves the bound session and directly wakes that exact terminal with one small adjustment plus pure Enter; it does not leave work in a passive inbox or create a packet. Continuation sends only the new instruction, semantic delta, delivery identity, Control session and short role recap; empty delta stays inline. Full packet recovery is only after compaction/interruption/authority uncertainty; init/payloads are not repeated. The launcher re-enumerates by exact Codex session ID, replaces stale handle metadata, reconciles its unbound ready/context-only Tasks by immutable packet digest, dispatches without recognition/injection and sends one pure Enter. It never parses composer text. Missing `agentIdentity`, user-takeover/detector/idle labels and old handles cannot release or replace a proved session. Only session absence permits fresh/full. Control performs no manual recovery.

Owner release is not discretionary cleanup. After every required review passes, guarded accept may return stable `OWNER_RELEASE_REQUIRED`; `advance`/`accept` then releases only the exact proven Owner, records confirmation, refreshes native state and retries acceptance. Idle time, cost, context size, `worker_done`, R0, reviewer activity and prospective `fix_local` never justify early release. Fresh one-shot Planner, R1/R2 and Luna/Synthesis sessions are released by the batch result path; Control performs no cleanup transition. This never applies to Research/Engineering merely because its first launch had `fresh_context=true`.

The only other release point is application of a semantically valid Planner proposal that changes the Owner's WP/affected closure. Guard must first prove there is no active affected dispatch and retained writer release is the sole remaining apply blocker; MATS resolves only affected current Owner identities, records their release, refreshes native state and retries the unchanged proposal. Unaffected Owners remain live. Unknown/mismatched identity blocks instead of broad cleanup.

`needs_synthesis` requires a validated, source-authored Synthesis request; Synthesis returns evidence to the retained Owner. Only the Owner can emit `plan_conflict` or a materially revised candidate. Reviewer `plan_conflict` forwards its source memo unchanged to Planner.

## Event table and refresh

| Native result | Required action |
|---|---|
| `question` with answer present in current packet/source evidence or deterministic MATS output | Reply with that evidence only; do not ask upward |
| Domain question lacking an authoritative answer | Forward once to its responsible Owner; ask the user only if the strict user-question boundary above is met |
| MATS format/hash/runtime/routing/session question | Use the injected public command locally; if it is absent/contradictory, report one noninteractive tool bug and stop—never edit MATS or ask user/Control to handcraft mechanics |
| `escalation` with declared routing outcome | Preserve the memo and apply that exact routing row |
| `worker_done` | Run the returned top-level `advance`; it imports the full batch, releases every confirmed one-shot before one acknowledgement, and continues the deterministic chain. Use `ready_results[].next_operation` only as exact single-step recovery |
| timeout/checkpoint | Treat as no event and issue the next event-driven wait |
| failed dispatch with immutable binding | Use exact-packet retry only after the retry preconditions above pass |
| native identity/lifecycle inconsistency | STOP; then load `native-boundary.md`; use exact help and only the documented last-resort `orca-cli` fallback |

Use `wait --control` for Control or the injected `wait --actor-packet` for an Owner. Start Control wait immediately after dispatch; no separate completion notification is needed. With no relevant active Dispatch, Control first claims any already-visible Run mail and otherwise returns the current deterministic `advance` state immediately; it never opens a blind 20-minute wait. With active work, it emits one pre-block notice and internally alternates bounded mail waits with exact Dispatch checks, without model commentary or TUI-idle inference. Pending `worker_done`/question/escalation always wins. A pure question/escalation delivery is acknowledged after capture and returned once; a batch containing `worker_done` remains pending until result import succeeds. A newer unimported Owner continuation takes precedence over an older imported blocked/failed result for that WP; only attempts at or before the source packet are obsolete. A successful current same-session context continuation that settles without mail is automatically resumed once. Any fresh/reviewer/failed/stopped/cancelled Dispatch that settles without an importable delivery returns `BLOCKED/LIFECYCLE_DELIVERY_MISSING` immediately; if another Control already imported it, wait returns the current `advance` state. Actor-packet wait remains mail-only. Do not send heartbeat/progress commentary or poll in parallel. The minimum/default outer timeout is 1,200,000 ms and applies only after real blocking begins. Reread exactly the nonempty `resume_anchor.required_rereads`. A verified checkpoint or worker completion needs no reread before its mechanical next operation; questions, escalations, semantic change, compaction/interruption or authority uncertainty retain refresh. A stale Owner anchor permits only return to Control.

MATS_WORKFLOW_EOF
