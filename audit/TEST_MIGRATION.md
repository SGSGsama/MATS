# Test intent migration through v17

The original v12 suite (94 tests) remains the historical baseline for semantic intent; duplicate scheduler/lease/outbox/cancellation authority is not resurrected merely to preserve old test names.

v17 preserves the v13-v16 semantic coverage: strict YAML/schema/path validation; project/WP/commitment identity; candidate vs acceptance; exact review target; R0 evidence freshness; R1/R2 routing; source-owned directives/memos; side-result consumption; synthesis identity; review-shopping/self-review prevention; precise plan invalidation; immutable artifacts; same-owner continuation; fresh judgment roles; effective model/effort checks; native completion not unlocking semantic downstream; and usage-accounting honesty.

v17 additionally covers the live-host failures found after v16:

- explicit custom Skill activation/load set without eager full Orca manual;
- deterministic child spawn for every role, including Owner-requested Luna Aux;
- first-launch inline Role Contract + reread path/digest;
- flexible instructions cannot override fixed binding/authority;
- `.task/bootstrap/<id>` placement while preserving separate bootstrap files;
- Windows path parts -> canonical POSIX logical refs;
- cross-platform local lock/atomic-write assumptions;
- native Run verification/bind before task-create;
- one-submit existing-terminal send;
- event-driven wait with >=20 minute timeout and checkpoint semantics;
- Planner Guard-generated contract checklist;
- early Planner schema/cross-field rejection with immutable rejected payload;
- exact `repair_of` planning occasion, no `.task` reset/archive bypass;
- mechanical `bin/mats planner-repair` request generation.

Current v17.1 grouped offline count: **172** (Semantics 78, Routing 44, Engineering/Loading/Usage 28, Spawn/Activation/Portability 22). Native/provider callbacks remain simulated; the count is not a model-quality claim.


v17.1 additionally verifies that Windows Git Bash/MSYS/Cygwin select the Skill-local Windows interpreter before any POSIX host-python fallback.
