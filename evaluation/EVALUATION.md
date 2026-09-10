# v17 evaluation protocol

No live model comparison, provider launch matrix, billing experiment, or quality non-inferiority study was run for v17. Unit/conformance tests prove implementation properties only.

Compare the same task corpus, source snapshot, tool access and acceptance rubric across: (A) native strong single-owner baseline, (B) prior managed baseline, and (C) v17 fixed-role policy. Count every Control session, owner native loop, context reread, Luna Aux, review, synthesis, Planner call, failed Planner proposal/repair, launch failure and human intervention. Compare cost per accepted success, latency, severe-error rate and rework—not token price alone.

## Control and Orca context accounting

Managed evaluation input to `usage_summary.py` must contain both `dispatches` and `control_sessions`. Record the final cumulative provider usage for every Control session. Its `input_tokens` and `cost_microusd` are authoritative and already include prompt/Skill context; never add static Skill sizes or context attribution a second time.

Every Control session records `context_loads` with unique `load_id`, `component`, observed `input_tokens`, `complete: true` and `included_in_control_input: true`. Component names use `mats:<name>` or `orca:<name>`. Record every Orca Skill actually loaded by the host, including automatic `orchestration`/`orca-cli` entrypoints when present. Repeated loads after a new session, compaction or refresh are separate events. Provider cached-input pricing remains represented by actual session cost, not a hand-applied token price.

Normal and anomaly paths remain separate. Normal accounting includes MATS activation, first-use storage when reached, and every Orca Skill the Control actually loaded. `native-boundary.md` and the full Orca guide count only for sessions where the declared native anomaly trigger occurred. Missing Control usage, a missing MATS/Orca context class, partial loads or unknown token/cost fields make the managed project total unknown rather than zero.

Run `context_footprint.py --mats-root ../skill/multi-agent-task-split --orca-skill orchestration=<path> [--orca-skill orca-cli=<path>] [--orca-full-guide-bytes <measured-bytes>]` to attribute UTF-8 source bytes. Include only actually loaded entrypoints; obtain full-guide bytes from the version-matched CLI output. This diagnostic is not a tokenizer or billing estimator; use it to detect prompt growth and explain provider-observed input, never as an additive cost total.

## Planner-specific ablation

Planner is the highest-cost role. Track:

- first-proposal schema/contract rejection rate;
- concept/ownership-boundary replan rate;
- repair calls per successful planning occasion;
- rejection causes (schema, commitment coverage, invalidation closure, stale base, invented commitment, WP boundary error);
- Astra tokens/cost per successfully applied plan change.

Compare v17 with and without the machine-derived `planner_contract_checklist`. The target is fewer avoidable contract retries without weakening Guard rejection rates.

## Activation / spawn / portability

Verify that a managed run actually loads the custom Control contract, uses `.task` semantic state, fixes every child model/effort, injects the correct Role Contract/path, and never substitutes native Orca `orchestration` for Skill activation. On Windows, verify canonical logical refs, local lock behavior, Skill-local Python path, Run binding before task-create, and one-submit terminal delivery.

## Event supervision

Check that managed completion uses blocking event waits, not worker/task/terminal polling. A 20-minute timeout must be recorded as a checkpoint and must not trigger retry, stop, failure or replacement by itself.
