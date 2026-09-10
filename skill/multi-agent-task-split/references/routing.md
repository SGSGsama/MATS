# Deterministic routing by semantic authority

Role selection uses validated operation, WP and request fields. Model and effort come only from launcher-private configuration behind `bin/mats dispatch`; Control never reads that configuration. `specialty` describes domain expertise; it grants no authority and changes no binding.

MATS owns decomposition, authority-role selection, WP ownership/scope, assignment, reassignment and review routing. A domain skill owns methodology inside the assigned packet. Its taxonomy cannot reassign work, launch workers, change bindings, widen scope or bypass review. A missing packet-declared `required_skill` produces a blocked Owner result naming that dependency.

These tables define semantic policy for Guard and `mats advance`; they are not instructions for Control to reimplement the transition engine. Control supplies only classifications or choices that `advance` returns as `NEEDS_DECISION`. Stable `reason_code`/`next_operation`, never diagnostic prose, identifies a mechanical route.

## Authority-role decision table

Apply the first row whose predicate is exactly true. If evidence satisfies multiple semantic rows or none, STOP for unresolved decomposition.

| Validated work product | Authority role | Fixed tuple | Write authority |
|---|---|---|---|
| Named MATS state/hash/gate/inventory command | Script | no model | Exact Control artifacts defined by that command |
| Coordination, event routing, transition selection | Control | Luna max | `.task` control operations only |
| Evidence/decision result with no repository product change | Research | Terra high | Declared research artifacts only |
| Repository/product change with required checks | Engineering | Terra high | Declared WP paths |
| Bounded bulk index/search/extract/triage satisfying every Aux predicate | Luna Aux | Luna max | none |
| Bounded source-backed evidence conflict/causal synthesis | Synthesis | Sol high | none |
| Ordinary independent candidate review | R1 | Terra high | none |
| Required system-invariant/cross-boundary gate | R2 | Sol high | none |
| Project commitments, WP boundaries or versioned project decisions | Planner | Astra xhigh | proposed semantic state only |

Ordinary bug investigation that leads into the same scoped fix/test outcome stays in one Engineering WP. Research requires a standalone evidence/decision exit condition, commonly reverse engineering, external measurement or protocol/format recovery; investigation order alone never creates a Research WP. Research may implement bounded analysis/probe/extraction scripts when their purpose and exit condition remain evidence. Shipping behavior, reusable product code, broad refactoring or build/release integration is Engineering.

The Script row is closed: it means only an installed `bin/mats` command that deterministically generates or verifies a MATS control artifact. Project binaries, builds, tests, benchmarks, reproducers, profilers, traffic generators, remote commands and interpretation of their output are domain execution, never Control work.

After MATS activation, task duration, apparent simplicity, read-only status, cost and dispatch overhead never change authority. A standalone evidence-only experiment with an independent exit condition is Research. A product test/benchmark -> diagnosis -> possible code change -> retest outcome is one Engineering WP: reuse its viable Owner, do not create a separate test WP, and do not let Control absorb the test.

Research and Engineering may run in parallel only when each has an independent exit condition, stable packet contract and non-conflicting scope, and current Engineering decisions do not depend on the unfinished Research conclusion. If Engineering must consume the pending Research conclusion, declare a Research -> Engineering dependency; only implementation independent of that conclusion may run concurrently.

## Cyber predicate

Set packet `cyber=true` iff the requested work product requires adversarial security reasoning about software, firmware, systems, protocols or binaries. Positive cases include vulnerability analysis, exploitability/root-cause assessment, reverse engineering, malware analysis, binary deobfuscation, security-control bypass analysis and security-focused protocol review. Incidental security terminology, ordinary auth feature implementation, generic reliability work and non-adversarial code review do not satisfy the predicate. Insufficient task evidence -> STOP for classification evidence; never guess from difficulty or `specialty`.

Control expresses a positive classification only with `dispatch -cyber`. It changes Sol-bound Synthesis/R2 to `gpt-daybreak-blue-latest` at the same effort. An explicit native primary-model-unavailable receipt permits one automatic Sol fallback; auth, quota, transport and other failures never trigger it. All other roles and efforts remain fixed.

## Delegation decision table

| Proposed dispatch | All required predicates | If any predicate is false |
|---|---|---|
| Initial Research/Engineering Owner | WP is unlocked; dependencies accepted; role matches WP; no conflicting active managed write access; MATS admission passes | Do not dispatch; report Guard/state fact |
| Active Owner user adjustment | Exact active same-WP Owner exists and the unchanged user text is subordinate to its current contract; use `steer --wp <WP> --instructions <text>` | Use the semantic/continuation route; never create a second active Owner |
| Existing Owner continuation/local repair | Exact unaccepted WP and in-scope directive/candidate still apply; no active dispatch exists for it; use `dispatch --continue-owner`; same workspace/access pass Guard | Retain it; do not fresh-spawn or perform native-loss recovery manually |
| Luna Aux | Source is a current Owner; request is read-only/mechanical; input is high-volume; output is verifiable against raw evidence; coverage/unknowns are preserved; request includes verification plan and benefit; it runs no project build/test/benchmark/reproducer, traffic generator or remote command | Owner performs work or returns a scoped blocker |
| Synthesis | Current Owner or reviewer produced a valid source request containing competing explanations, attempts, evidence and a decision key | Return request validation error to source role |
| R1 | Exact candidate passed R0; no R1 record exists for that candidate | Run R0 or retain existing review |
| R2 | Exact candidate has no R2 record and R1 returned `escalate_r2` or Guard returned `reason_code=R2_REQUIRED` | Do not dispatch R2 |
| Planner | Exactly one Planner trigger row below is true and its required source refs/directives exist | Keep current plan; do not dispatch Planner |
| Exact-packet retry | Packet ref/digest resolves; at least one immutable binding exists; the MATS-refreshed native view marks every bound dispatch `failed`; no fresh semantic/continuation argument is supplied | STOP; inspect unknown/running/successful delivery or create the correct non-retry transition |

Native placement does not change authority. When nested depth allows Owner placement, the Owner runs the same launcher; otherwise Control runs the unchanged source request.

Luna Aux is optional cost advice, never a mandatory transition or substitute for a small Research/Engineering Owner. An Owner may use it when bulk mechanical indexing/search/extraction will save context; direct reading is always valid. Not using Aux never causes blocked status. A user condition requiring approval before an external push, deploy, restart or replacement is an Owner stop condition: the Owner asks before that mutation, Control forwards the question unchanged and waits, and Control never performs the mutation.

`scope.paths` is the Owner write boundary. `scope.refs` and packet evidence are navigation advice, never read permissions or an exhaustive allowlist. Any role may inspect task-relevant sources allowed by the environment without Control/Planner/user approval. Candidate checks never validate an old `scope.refs` content pin; stale or missing seed input cannot block delivery. If an Owner actually relies on a source, it cites that path in delivery evidence, and MATS pins its current content separately from product changes. No read grant, plan/version change or new packet exists. Never label Owner-produced out-of-scope output as read evidence. Do not edit `scope.refs`, invoke Planner, or apply an already-issued proposal merely to attach/read evidence. Required writes, other-WP ownership or changed commitments/dependencies are Planner decisions.

## Review result transition table

| Verified result | Next action |
|---|---|
| R1 `pass` | Invoke guarded accept on exact candidate |
| Guarded accept returns `reason_code=R2_REQUIRED` | Dispatch R2 on exact candidate |
| R1 `escalate_r2` | Dispatch R2 on exact candidate |
| R1/R2 `fix_local` | Continue the same role/WP/session with `--continue-owner`; require materially revised candidate before new review |
| R1 `needs_synthesis` | Dispatch validated Synthesis request; return result to Owner |
| R1/R2 `plan_conflict` | Preserve source memo and dispatch Planner only if Planner trigger validates |
| R2 `pass` | Guarded accept exact candidate |

Owner `structural_tags` are explicit R2 triggers, not domain, difficulty or importance labels. Use one only when a candidate may be locally correct while violating a relationship outside its local proof. The closed set covers architecture topology, milestone integration, cross-module contracts, public API and persistent compatibility, protocol semantics, end-to-end behavior, state/resource ownership, failure/recovery behavior, cross-platform compatibility and cryptographic contracts shared across components or versions. Local algorithm difficulty, complex tooling, file count and directory names do not qualify. Guard never infers structural risk from path names.

`references/r2-tags.yaml` is the single definition source. MATS pins and projects it into packets: Owner and R1 receive the compact catalog needed to select or detect a trigger; R2 receives only definitions for the candidate's selected tags plus mechanical non-tag trigger reasons. R2 never loads the full catalog. Control does not read this reference or interpret tags.

R1 owns local candidate correctness. R2 asks the distinct system question that R1 may not cover: can this locally valid result make a downstream consumer, another WP, another state/phase, another platform or an end-to-end path wrong? Guard computes the R2 requirement from packet/WP review policy and impact, the candidate's explicit R2 tags, and R1 outcome. Control consumes only the guarded transition result. Synthesis is advisory and never becomes R2 or implementation Owner.

## Planner trigger table

| Trigger | Required evidence | Planner mode |
|---|---|---|
| Initial semantic state absent | Canonical bootstrap inputs and repository inventory | Full bootstrap |
| Explicit user change to a commitment, WP objective/owner/write boundary/dependency/exit condition/review policy, or milestone | Immutable raw directive with `project_steer` intent plus the exact materialized project/plan field it supersedes | Patch |
| Source-backed `plan_conflict` | Valid Owner/reviewer memo naming affected commitments/WPs | Patch |
| Phase/milestone boundary | Accepted prerequisite set plus a stated project-level decision; a new long-lived namespace additionally requires request-pinned `target_milestone_id=m<current+1>_<milestone-slug>` | Patch |
| Stall | Repeated evidenced attempts under the same WP contract plus a blocker requiring changed commitment/scope/dependency | Patch |
| Planner output Guard rejection | Immutable rejection and rejected-result refs; mechanically generated unchanged-base repair request | Same occasion: full for unconsumed bootstrap, otherwise patch |

Control never opens product files or interprets domain evidence to manufacture a Planner trigger. A request's protocol/API/architecture impact, test work, added log or behavior correction is not sufficient by itself. For an unaccepted WP with a viable retained Owner, route it unchanged to that Owner unless the raw directive explicitly supersedes a cited current project/plan field; the Owner/reviewer may instead return source-backed `plan_conflict`. When Planner is valid, its question is neutral: quote the source meaning and cite current state, but do not add Control-selected design, implementation, compatibility, fallback, test or acceptance decisions. Ambiguity is a Planner decision input, not permission for Control to resolve it.

Local difficulty, token pressure, worker timeout, failed native launch, model availability and desire for a stronger model are never Planner triggers. Binding changes belong to the offline operator release process; runtime budget does not weaken review or select a different model.

MATS_ROUTING_EOF
