# MATS v17.4 Review 证据索引

本文件汇总当前源码片段与此前 review 包中的本地模拟记录。原始源码未修改；本轮没有重新运行测试。

原始归档 SHA-256：`3e2f947946b80ba097e1668f7049bd92545ea117cbff9fff4f5fd645a25c5ace`。

## 1. 先前测试和模拟记录

### targeted_suite_summary.json

```
{
  "tests_run": 8,
  "failures": 0,
  "errors": 0,
  "skipped": 0,
  "seconds": 3.556,
  "tests": [
    "test_spawn.DeterministicSpawn.test_packet_retry_requires_a_prior_native_failed_binding",
    "test_spawn.DeterministicSpawn.test_packet_retry_rejects_fresh_semantic_overrides",
    "test_spawn.DeterministicSpawn.test_r1_one_shot_release_failure_keeps_completion_for_same_result_retry",
    "test_spawn.DeterministicSpawn.test_worker_done_wait_stages_one_argument_result_import_and_ack",
    "test_spawn.DeterministicSpawn.test_r2_worker_done_import_is_acknowledged_from_reviews_collection",
    "test_spawn.DeterministicSpawn.test_ack_failure_keeps_staging_for_idempotent_retry",
    "test_spawn.DeterministicSpawn.test_checkpoint_wait_returns_compact_control_and_owner_resume_anchors",
    "test_semantics.CandidateAndReview.test_duplicate_binding_is_idempotent"
  ]
}
```

### probe_retry_result.json

```
{
  "scenario": "retry packet has a prior binding, but no native failed confirmation",
  "rejected": true,
  "error": "reusing a dispatch packet requires native-confirmed failed attempts; inspect unknown/successful delivery first",
  "original_draft_preserved": false,
  "native_task_create_calls": 0,
  "native_start_calls": 0,
  "replacement_prefix": "MATS-FORM\t1\tresult\n# Fill column values; keep the header and row names. Add repeatable rows as needed.\n# Rows: status, summary, impact, evidence/evide"
}

```

### probe_batch_result.json

```
{
  "scenario": "two review_r1 completions in one native delivery batch",
  "review_dispatch_ids": [
    "D7",
    "D15"
  ],
  "released_dispatch_ids": [
    "D15"
  ],
  "ack_calls": 1,
  "remaining_completion_staging": [],
  "remaining_delivery_files": 0,
  "imports": [
    {
      "dispatch_id": "D7",
      "rc": 0,
      "stdout": {
        "result_ref": {
          "path": "m0_baseline/reviews/f37f3e7ff4b4492dc41bef3bb7744fb95fd4835b1114edf8a1fc90be4e364338-review_r1.yaml",
          "sha256": "c3c839e624ae7c3fc3910cc787beed954777ce6237648aefffaff45e1624c399"
        },
        "worker_done_acknowledged": false
      },
      "stderr": ""
    },
    {
      "dispatch_id": "D15",
      "rc": 0,
      "stdout": {
        "one_shot_session_released": true,
        "result_ref": {
          "path": "m0_baseline/reviews/c29046142c098de47a6b48fd9f8fb8638281a8f2b16f07e57c3aaab876a654f8-review_r1.yaml",
          "sha256": "0a8832a06598ed7e714eaf8b45675477fa04342ea976eee607320a94a3fa7dc7"
        },
        "worker_done_acknowledged": true
      },
      "stderr": ""
    }
  ]
}

```

### new_invariant_tests.txt

```
test_batch_ack_requires_release_of_every_one_shot_reviewer (test_protocol_invariants.ProtocolInvariants.test_batch_ack_requires_release_of_every_one_shot_reviewer) ... FAIL
test_rejected_retry_does_not_overwrite_existing_owner_delivery (test_protocol_invariants.ProtocolInvariants.test_rejected_retry_does_not_overwrite_existing_owner_delivery) ... FAIL

======================================================================
FAIL: test_batch_ack_requires_release_of_every_one_shot_reviewer (test_protocol_invariants.ProtocolInvariants.test_batch_ack_requires_release_of_every_one_shot_reviewer)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/mnt/data/mats_review/test_protocol_invariants.py", line 76, in test_batch_ack_requires_release_of_every_one_shot_reviewer
    self.assertEqual(set(release_ids_at_ack[0]), set(reviewer_ids),
    ~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                     'Do not acknowledge/clear a batch while another one-shot release is pending.')
                     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: Items in the second set but not the first:
'D7' : Do not acknowledge/clear a batch while another one-shot release is pending.

======================================================================
FAIL: test_rejected_retry_does_not_overwrite_existing_owner_delivery (test_protocol_invariants.ProtocolInvariants.test_rejected_retry_does_not_overwrite_existing_owner_delivery)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/mnt/data/mats_review/test_protocol_invariants.py", line 33, in test_rejected_retry_does_not_overwrite_existing_owner_delivery
    self.assertEqual(delivery.read_bytes(), original,
    ~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                     'A rejected retry must not reset an existing attempt delivery.')
                     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: b'MATS-FORM\t1\tresult\n# Fill column value[522 chars]\t\n' != b'OWNER_WORK_IN_PROGRESS_DO_NOT_REPLACE\n' : A rejected retry must not reset an existing attempt delivery.

----------------------------------------------------------------------
Ran 2 tests in 1.769s

FAILED (failures=2)

```

## 2. 当前归档源码（路径相对 skill/multi-agent-task-split/）

### references/workflow.md:11–43

```text
11: ## Control state machine
12:
13: At each step Control reads current semantic state and the routing tables, then executes one matching transition. Native-dependent MATS commands refresh and normalize their own runtime view. More than one matching row, no matching row, incomplete evidence or ambiguous classification -> STOP and report the unresolved inputs.
14:
15: | Current condition | Required next action | Next condition |
16: |---|---|---|
17: | `LOAD_COMPLETE` is false | Finish activation; no project action | `LOAD_COMPLETE` or STOP |
18: | No valid `.task/semantic.yaml` | Run `milestone-paths`, write only its exact `goal.txt`, then run `bootstrap-init`; dispatch its returned Planner request | Planner running |
19: | Valid semantic state; active managed dispatch exists | `wait --control` | Event/checkpoint received |
20: | Valid semantic state; no active dispatch; unprocessed verified event exists | Apply the event table below | State selected by event |
21: | In-scope user continuation, test request or evidence/log addition targets an unaccepted WP with a viable retained Owner and no active dispatch | Pass the directive unchanged with `dispatch --continue-owner`, without product inspection or domain judgment; preserve every stated external-mutation approval condition | Owner running |
22: | Valid semantic state; no active dispatch/event; eligible unlocked WP exists | Dispatch its declared Research/Engineering Owner | Owner running |
23: | Owner result imported as candidate | Run R0 on the content-pinned candidate | R0 pass or STOP |
24: | R0 passed; no R1 for exact candidate | Dispatch fresh R1 | R1 running |
25: | R1 returned `pass` | Invoke guarded accept while retaining Owner | Exact `passing R2 required`, exact `affected writer terminal is still live; worker_done is not writer release`, or STOP |
26: | R1 returned `escalate_r2`, or accept returned exact `passing R2 required` | Dispatch fresh R2 | R2 running |
27: | All required reviews passed; accept reports exact `affected writer terminal is still live; worker_done is not writer release` | Release that Owner session, then repeat guarded accept | Accepted or STOP |
28: | R2 passed | Guarded accept while retaining Owner, then apply the release row above | Accepted or STOP |
29: | Accepted WP unlocks a dependency | Re-evaluate this table from current state | One next transition |
30: | All WPs accepted | Report completion from accepted artifacts | Complete |
31: | Guard rejection | STOP current transition; preserve the rejection and use only its documented recovery | Unchanged semantic state |
32:
33: Control never performs Owner, Synthesis, Reviewer or Planner reasoning or executes domain commands. It reads current MATS semantic/control artifacts for transitions, but never searches/opens product source, binaries, raw domain logs/evidence or worker transcripts to diagnose work. The Script authority is limited to named MATS CLI operations defined in `routing.md`; work size, cost and read-only status never widen it. A domain skill supplies methods inside an already selected packet; it never selects a state-machine transition.
34:
35: Questions never create Planner occasions. Route test requests, evidence/log additions, behavior corrections and reversible in-scope details to the retained Owner without confirmation or prior domain investigation. Control may compare a directive only with the materialized project/plan; product impact, protocol/API/architecture vocabulary or Control's own implementation inference never proves a Planner trigger. If the current semantic state does not explicitly conflict, the Owner receives the directive and returns `plan_conflict` only when its contract truly must change. For a valid Planner occasion, preserve the immutable user/source text and write a neutral decision question. Control may add only MATS-required structure, exact cited current-state facts and explicit user authority limits. It never turns an ambiguous term into an architecture, protocol/frame format, compatibility/fallback policy, algorithm, test design or acceptance rule; those remain Planner decisions. Read paths are advisory and need no Control grant; old `scope.refs` hashes are not candidate gates, while sources actually cited by the Owner are pinned at delivery. If an already-running Planner was mistakenly opened only for such local steering, close its exchange without applying the proposal, then continue the Owner. Resolve MATS schema/ref/hash/snapshot/runtime/routing/retry/session mechanics locally from its command/result. Ask the user once, with all missing items, only for a goal/authority decision or irreversible/external mutation approval unavailable from authoritative sources.
36:
37: For a valid non-bootstrap Planner occasion, run `planning-request-form`, fill only its semantic TSV cells, then run its returned `planning-request` operation and dispatch the returned immutable request path. Directive `raw_text` stays verbatim and the question stays neutral. MATS stores the directives and generates request schema, refs, hashes and filenames; Control never authors directive/planning-request YAML or path/hash wrappers. `planner-repair` remains fully generated from the immutable rejection and requires no form editing by Control.
38:
39: Normal native preparation is one MATS command. Never test for `.task/tmp/runtime-view.yaml`, ask the host to create it, call raw `orca open/status`, inspect processes, re-run `control`, or load the full Orca guide before `dispatch`, `accept` or `apply-plan`. Those commands start Orca at most once when needed, resolve the current workspace/access, capture a compact view and run Guard internally. The fixed runtime-view file is only overwritten script output. A returned native error is the only anomaly input; do not infer permission-context or connectivity faults from a missing file.
40:
41: ## Control path invariant
42:
43: At `LOAD_COMPLETE`, bind the exact host workspace repository and pass it with `--repo` on every MATS command. That repository is the only Control path root; shell CWD, a previously visited directory and host temp never grant write authority. Every Control-created log, capture or redirect uses one fixed reused path under that repository's `.task/tmp`; Control writes no external path.
```

### references/roles/control.md:1–7

```text
1: Identity: Control coordinator.
2: Owns: role/WP assignment and guarded transitions.
3: May: read named MATS state; classify cybersecurity work for `dispatch -cyber`; manage current-repo `.task/tmp`; continue the exact live same-WP Owner even when Orca labels it external/user-takeover.
4: Must not: decide truth; expand directives with design choices; inspect/search product source, binaries, raw domain logs/evidence or terminal transcripts; edit products or run build/test/benchmark/reproducer/traffic/remote work; write outside `.task/tmp` except via MATS; choose bindings; inspect CLI internals; author transactions/`worker_done`; or release a retained Owner before Guard proves writer release is the sole acceptance blocker. No recovery, contract conflict, or script/transaction edit/Guard bypass => STOP and report the tool bug; never improvise or ask user to do MATS mechanics. No size/cost/read-only exception. Takeover alone is not Owner loss.
5: Output: only the next action selected by current state and the routing tables.
6: Handoff: domain to Owner; commitments to Planner; gates to R1/R2.
7: Refresh: resume-anchor paths; after compaction/interruption/semantic/authority uncertainty.
```

### scripts/role_spawn.py:276–289

```text
276:     hydrated_packet=hydrate(g.files,pref)
277:     delivery_prefill=None
278:     if packet['role']=='planner' and packet.get('request',{}).get('repair_of'):
279:         feedback=hydrated_packet.get('planner_repair_feedback')
280:         if not isinstance(feedback,dict) or not isinstance(feedback.get('rejected_result_ref'),dict):
281:             raise Rejected('Planner repair packet lacks its exact rejected-result prefill')
282:         delivery_prefill=g.files.get(feedback['rejected_result_ref'])
283:     delivery_path=g.files.delivery_path(packet['id'],create=True)
284:     atomic_write(delivery_path,render_form(hydrated_packet,prefill=delivery_prefill))
285:     continuation = terminal is not None
286:     prior_receipt=reuse_receipt if reuse_receipt is not None else _prior_packet_receipt(g,pref) if retry else None
287:     inferred_access=prior_receipt['access'] if prior_receipt else _packet_access(g,packet)
288:     if access is not None and access!=inferred_access:
289:         raise Rejected(f'access is launcher-owned for this packet: expected {inferred_access}')
```

### scripts/role_spawn.py:343–414

```text
343:     if dry_run:
344:         return preview
345:     with g.files.lock():
346:         if runtime_view is None:
347:             runtime_view,_runtime_path=capture_runtime_view(g,cli)
348:         if workspace_key is None:
349:             workspace_key=resolve_workspace_key(cli,g.files.repo,worktree)
350:         if managed_owner_continuation:
351:             retained=any(u['session_id']==reuse_receipt['session_id'] for u in runtime_view['workspace_users'])
352:             if retained:
353:                 admission=g.preflight(pref,runtime_view,workspace_key,access,reuse_session=reuse_receipt['session_id'],require_failed_retry=False)
354:                 terminal,retained_owner_probe=retained_terminal_handle(cli,reuse_receipt)
355:             else:
356:                 admission=g.preflight(pref,runtime_view,workspace_key,access,reuse_session=None,require_failed_retry=False)
357:                 terminal=None;continuation=False
358:                 native_recovery={'reason':'retained_owner_absent','replaced_dispatch_id':reuse_receipt['dispatch_id']}
359:                 prompt=initial_prompt(packet,pref,repo=g.files.repo,policy=g.policy(),instructions=instructions,
360:                                       recovery='the retained Owner was absent')
361:                 prompt_mode='full'
362:         else:
363:             admission = g.preflight(pref, runtime_view, workspace_key, access, reuse_session=(reuse_receipt or {}).get('session_id'),require_failed_retry=retry)
364:         preview['admission']=admission;preview['prompt']=prompt;preview['prompt_mode']=prompt_mode
365:         run_context = ensure_run_context(cli, g.state()['run_id'])
366:         task = create_task(cli,prompt)
367:         try:
368:             task_id = task['result']['task']['id']
369:         except (KeyError, TypeError):
370:             raise Rejected('task-create receipt lacks result.task.id')
371:         argv = launch_argv(g.policy(), packet['role'], task_id, worktree, cli=cli, terminal=terminal, reuse_receipt=reuse_receipt, cyber=cyber)
372:         fallback_argv = launch_argv(g.policy(), packet['role'], task_id, worktree, cli=cli, cyber=cyber, fallback=True) if fallback_binding and not continuation else None
373:         try:
374:             start = start_worker(argv,fallback_argv=fallback_argv) if fallback_argv else start_worker(argv)
375:         except AgentUnconfigured as lost:
376:             if not managed_owner_continuation:
377:                 raise
378:             # user-takeover/external means Orca no longer owns this terminal; it does
379:             # not mean the process, session or same-WP Owner disappeared.  Rebind the
380:             # already-created Task to the exact attested terminal.  Never release or
381:             # replace a viable Owner merely because worker-start cannot configure it.
382:             start=dispatch_existing_terminal(cli,task_id,terminal)
383:             native_recovery={'reason':'agent_unconfigured_same_terminal_rebind',
384:                              'retained_dispatch_id':reuse_receipt['dispatch_id'],
385:                              'terminal':terminal,'native_error':str(lost)}
386:         fallback_used=bool((start.get('_mats_model_fallback') or {}).get('used'))
387:         actual_expected=fallback_binding if fallback_used else expected
388:         effective = reuse_receipt['effective'] if continuation else _effective(start)
389:         did = _dispatch_id(start)
390:         if effective != actual_expected:
391:             stop = None
392:             if did and not continuation:
393:                 try: stop = stop_worker(cli,did)
394:                 except Exception as e: stop = {'stop_error': str(e)}
395:             raise Rejected(f'ROLE_BINDING_UNVERIFIED expected={actual_expected} effective={effective} dispatch={did} stop={stop}')
396:         if not did: raise Rejected('worker-start receipt lacks dispatchId')
397:         shown=worker_show(cli,did)
398:         canonical=normalize_launch_receipt(start,shown,packet_digest=pref['sha256'],access=access,fresh_context=not continuation,effective=effective,
399:                                            model_fallback=start.get('_mats_model_fallback'),simulation=g.state()['simulation'],
400:                                            source='MATS normalized public same-terminal Orca dispatch + worker-show' if native_recovery and native_recovery.get('reason')=='agent_unconfigured_same_terminal_rebind' else None)
401:         if canonical['workspace_key']!=workspace_key:
402:             if not continuation:
403:                 try:stop_worker(cli,did)
404:                 except Exception:pass
405:             raise Rejected(f'native launch used another workspace: expected={workspace_key} actual={canonical["workspace_key"]}')
406:         if continuation and canonical['session_id']!=reuse_receipt['session_id']:
407:             raise Rejected(f'owner continuation changed native session identity: expected={reuse_receipt["session_id"]} actual={canonical["session_id"]}')
408:         try:
409:             binding_ref=g.bind(pref,canonical)
410:         except Exception:
411:             if not continuation:
412:                 try: stop_worker(cli,did)
413:                 except Exception: pass
414:             raise
```

### scripts/dispatchctl.py:176–196

```text
176:             elif a.cmd=='result':
177:                 binding_ref=_internal_ref(g,a.binding_ref,'bindings')
178:                 if bool(a.result)!=bool(a.completion):raise Rejected('normal result import takes only binding_ref; legacy mode requires both result and completion files')
179:                 if a.result:
180:                     out=g.import_result(binding_ref,_task_load(g,a.result),_task_load(g,a.completion))
181:                 else:
182:                     binding=g.files.get(binding_ref);result_ref,event=g.import_staged_result(binding_ref)
183:                     acknowledged=False;ack_error=None;released=None;release_error=None
184:                     if g.completion_batch_imported(event):
185:                         if binding['role'] in ONE_SHOT_ROLES:
186:                             try:release_worker(a.cli,binding['receipt']['dispatch_id']);released=True
187:                             except Rejected as exc:release_error=str(exc)
188:                         if release_error is None:
189:                             try:acknowledge_events(a.cli,event['delivery_id']);acknowledged=True;g.clear_completion_batch(event)
190:                             except Rejected as exc:ack_error=str(exc)
191:                     out={'result_ref':result_ref,'worker_done_acknowledged':acknowledged}
192:                     record=g.files.get(result_ref);side_refs=([record['side_request_ref']] if record.get('side_request_ref') else g.side_requests_for_binding(binding_ref))
193:                     if side_refs:out['source_side_request_refs']=side_refs
194:                     if released is not None:out['one_shot_session_released']=released
195:                     if release_error:out['release_retry']='rerun the same idempotent result command; '+release_error
196:                     if ack_error:out['acknowledgement_retry']='rerun the same idempotent result command; '+ack_error
```

### scripts/guards.py:686–702

```text
686:     def completion_batch_imported(self,record):
687:         dispatches=record.get('batch_worker_done_dispatches')
688:         if not isinstance(record.get('batch_has_other_events'),bool) or not isinstance(dispatches,list) or not dispatches:
689:             raise Rejected('invalid normalized worker_done batch metadata')
690:         for dispatch_id in dispatches:identifier(dispatch_id)
691:         if len(set(dispatches))!=len(dispatches):raise Rejected('invalid normalized worker_done batch metadata')
692:         return not record['batch_has_other_events'] and all(self.imported_dispatch_ref(x) is not None for x in dispatches)
693:
694:     def clear_completion_batch(self,record):
695:         """Remove only script-owned tmp inputs after import and native acknowledgement."""
696:         with self.files.lock():
697:             for dispatch_id in record['batch_worker_done_dispatches']:
698:                 path=self.files.completion_event_path(dispatch_id);path.unlink(missing_ok=True)
699:                 binding_ref=self.files.named('bindings',dispatch_id)
700:                 if binding_ref:
701:                     packet=self.files.get(self._binding(binding_ref)['packet_ref'])
702:                     self.files.delivery_path(packet['id']).unlink(missing_ok=True)
```

### scripts/guards.py:822–841

```text
822:     def accept(self,wp_id,view):
823:         with self.files.lock():
824:             s=self.state();self._view(s,view);self._control(s)
825:             ref=s['current_candidates'].get(wp_id)
826:             if not ref: raise Rejected('no current candidate')
827:             c=self.files.get(ref);self.verify_candidate(c,s);self._validate_consumption(c,s)
828:             r0=self.files.named('r0',ref['sha256'])
829:             if not r0 or not self.files.get(r0)['passed']: raise Rejected('R0 failed/missing')
830:             r1=self.review_record(ref,'review_r1');need=self.needs_r2(c,s,r1)
831:             if not r1 or r1['result']['outcome'] not in ({'pass','escalate_r2'} if need else {'pass'}): raise Rejected('R1 does not permit acceptance')
832:             if need:
833:                 r2=self.review_record(ref,'review_r2')
834:                 if not r2 or r2['result']['outcome']!='pass': raise Rejected('passing R2 required')
835:             for role in ['review_r1']+(['review_r2'] if need else []):
836:                 r=self.review_record(ref,role);rb=self._binding(r['binding_ref'])
837:                 for f in r['result']['findings']: verify_evidence(Path(rb['receipt']['workspace_path']),f['evidence'],self.policy(s)['evidence_roots'])
838:             require_drained(view,{wp_id})
839:             self.verify_candidate(c,s)
840:             s['accepted'][wp_id]={'candidate_ref':ref,'accepted_under_plan':s['plan']['version'],'review':'r2' if need else 'r1'}
841:             self.files.commit(s);return s['accepted'][wp_id]
```

### scripts/packets.py:176–221

```text
176:     # Envelopes stay small; externalization preserves bytes but does not make hydration free.
177:     spill=['planner_repair_feedback','source_artifacts','directives','since_last_planner','bootstrap_inventory','plan','project','previous_reviews','previous_candidate','candidate','source_request','upstream','direct_downstream']
178:     for field in spill:
179:         if len(encode(body))<=p['packet_limits'][role]-256: break
180:         if field in body: externalize(field, required=True)
181:     if len(encode(body))>p['packet_limits'][role]-256:
182:         raise Rejected('packet envelope exceeds role limit; explicitly scope attachments, never truncate source text')
183:     return body
184:
185:
186: def hydrate(files,packet_ref,*,include_available=False):
187:     body=files.get(packet_ref).copy()
188:     refs=list(body.get('required_payload_refs',[]))
189:     if include_available: refs += list(body.get('available_payload_refs',[]))
190:     for part in refs:
191:         if part['field'] in body: raise Rejected('payload would overwrite a field')
192:         body[part['field']]=files.get(part['ref'])
193:     return body
194:
195:
196: _CONTINUATION_FIXED_FIELDS=frozenset({
197:     'schema_version','id','role','authority_role','specialty','cyber','wp_id','run_id','project_id',
198:     'policy_digest','state_view','plan_version','contract_digest','role_contract_path',
199:     'role_contract_digest','boundary','artifact_root','output_contract','delivery_validation',
200:     'schema_on_demand','required_payload_refs','available_payload_refs',
201: })
202:
203:
204: def continuation_delta(files,base_ref,current_ref):
205:     """Return the lossless semantic difference a retained Owner must newly read.
206:
207:     Full packets remain immutable Guard inputs.  Model context reuses the already
208:     loaded base packet and reads only this content-addressed projection in normal
209:     continuation.  A future field is included automatically unless explicitly
210:     classified as fixed transaction/authority metadata above.
211:     """
212:     base=hydrate(files,base_ref,include_available=True)
213:     current=hydrate(files,current_ref,include_available=True)
214:     if base.get('role') not in OWNERS or current.get('role')!=base.get('role') or current.get('wp_id')!=base.get('wp_id'):
215:         raise Rejected('Owner continuation delta requires the same role and WP')
216:     keys=(set(base)|set(current))-_CONTINUATION_FIXED_FIELDS
217:     changed={key:copy.deepcopy(current[key]) for key in sorted(keys) if key in current and base.get(key)!=current[key]}
218:     removed=sorted(key for key in keys if key in base and key not in current)
219:     return {'schema_version':1,'kind':'owner_continuation_delta','base_packet_ref':base_ref,
220:             'current_packet_ref':current_ref,'changed':changed,'removed':removed,
221:             'read_rule':'Apply changed/removed to the already-loaded base packet. Open the full current packet only after compaction, interruption or authority uncertainty.'}
```

### scripts/records.py:130–144

```text
130:     def next_index(self,folder,prefix='p'):
131:         identifier(folder);identifier(prefix)
132:         pat=re.compile(re.escape(prefix)+r'([0-9]{6})')
133:         values=[int(m.group(1)) for ref,_ in self.all(folder) if (m:=pat.fullmatch(Path(ref['path']).stem))]
134:         return f'{prefix}{(max(values,default=0)+1):06d}'
135:
136:     def read(self): return load(contained(self.root,'semantic.yaml'))
137:     def read_operator(self): return load(contained(self.root,'operator.yaml'))
138:     def write_operator(self,value):
139:         validate('operator_control', value)
140:         atomic_write(contained(self.root,'operator.yaml'),encode(value))
141:     def commit(self,state):
142:         data=encode(state)
143:         if len(data)>4*1024*1024: raise Rejected('semantic document exceeds 4 MiB; archive a project boundary')
144:         atomic_write(contained(self.root,'semantic.yaml'),data)
```

### scripts/records.py:175–183

```text
175:     def all(self,folder):
176:         identifier(folder)
177:         roots=[contained(self.root,folder)]
178:         for d in self.root.glob('m*'):
179:             if d.is_symlink(): raise Rejected('symlink in milestone artifact directory')
180:             if d.is_dir() and MILESTONE_ID.fullmatch(d.name):roots.append(d/folder)
181:         paths=sorted(p for root in roots if root.exists() for p in root.glob('*.yaml'))
182:         if any(p.is_symlink() for p in paths): raise Rejected('symlink in semantic artifact directory')
183:         return [({'path':logical_relative(self.root,p),'sha256':digest(load(p))},load(p)) for p in paths]
```

### scripts/routing.py:85–106

```text
85:     if role == 'synthesis' and (not request['attempted'] or not request['evidence']):
86:         raise Rejected('synthesis needs prior local work and pinned evidence')
87:     return role
88:
89: def next_review(outcome):
90:     # A role is not an escalation ladder; each result has one semantic next action.
91:     return {'pass':'accept_or_r2', 'fix_local':'owner', 'needs_synthesis':'synthesis_then_owner',
92:             'escalate_r2':'review_r2', 'plan_conflict':'planner'}[outcome]
93:
94: def fixed_binding(policy,role):
95:     if role not in ROLES: raise Rejected('unknown role')
96:     return dict(policy['bindings'][role])
97:
98: def dispatch_bindings(policy,role,*,cyber=False):
99:     """Resolve the launcher-owned primary and the sole permitted fallback.
100:
101:     ``cyber`` is a semantic task classification supplied by Control, never a
102:     model override. It only replaces roles whose fixed model is Sol and keeps
103:     that role's configured effort unchanged.
104:     """
105:     if type(cyber) is not bool: raise Rejected('cyber classification must be boolean')
106:     base=fixed_binding(policy,role)
```
