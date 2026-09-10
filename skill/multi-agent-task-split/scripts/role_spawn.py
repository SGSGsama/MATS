"""Deterministic launcher for every managed child role.

The caller supplies semantic operation + optional call-specific instructions. This
script owns role resolution, fixed model/effort, full first-launch role injection,
compact same-Owner continuation, native Task creation and lifecycle argument
construction. It never guesses task difficulty or accepts a model override.
"""
import argparse, os, re, sys
from pathlib import Path
SCRIPTS=Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:sys.path.insert(0,str(SCRIPTS))
if __name__=='__main__' and Path(sys.prefix).resolve() != (SCRIPTS.parent/'.venv').resolve():
    print('MATS_RUNTIME_ERROR: use the installed bin/mats launcher',file=sys.stderr);raise SystemExit(126)

from common import ROOT, Rejected, atomic_write, digest, emit_utf8, load, logical_relative, rejection_payload, require_managed_runtime
from forms import render_form
from guards import Guards
from packets import continuation_delta, hydrate
from routing import OWNERS, dispatch_bindings, launch_argv
from native_orca import capture_runtime_view, create_task, dispatch_context_task, ensure_run_context, fail_task, resolve_workspace_key, retained_terminal_handle, start_worker, stop_worker, tasks_with_status, terminal_send, terminal_submit, worker_show, normalize_effective, normalize_launch_receipt

REMOTE_EVIDENCE_RULE='Required remote evidence unavailable: directly request the exact missing item via the native preamble; never guess or blame MATS/Guard.'
DELIVERY_SUFFIX='deliver <packet-id>'



def _instructions(g, path, text):
    if path and text:
        raise Rejected('use either --instructions-file or --instructions, not both')
    if path:
        p = g.files.control_path(path,prefixes=('tmp',))
        if not p.is_file():
            raise Rejected('instructions file not found under .task')
        return p.read_text(encoding='utf-8').strip()
    return (text or '').strip()


def _request_argument(g, operation, value):
    if value is None:return None
    if operation not in {'luna_aux','synthesis'}:
        return g.files.load_control(value)
    candidate=Path(value)
    if len(candidate.parts)==1 and candidate.suffix.lower() not in {'.yaml','.yml'}:
        ref=g.files.named('requests',value)
        if ref is None:raise Rejected('side request artifact ID not found')
        return ref
    path=g.files.control_path(value,prefixes=('requests',));logical=logical_relative(g.files.root,path)
    if not g.files.is_folder_path(logical,'requests'):
        raise Rejected('side request must be a milestone-nested artifact; ref-wrapper files are not accepted')
    return {'path':logical,'sha256':digest(load(path))}


def _prompt_material(packet, packet_ref, repo):
    role = packet['role']
    if role == 'control':
        raise Rejected('Control is the root session and is never child-spawned')
    role_path = (ROOT / 'references' / 'roles' / f'{role}.md').resolve()
    role_path_text = role_path.as_posix()
    contract = role_path.read_text(encoding='utf-8').strip()
    if packet.get('role_contract_digest')!=digest(contract) or Path(packet.get('role_contract_path','')).resolve()!=role_path.resolve():
        raise Rejected('packet role contract does not match installed role contract')
    if 'role_contract' in packet:
        raise Rejected('inline legacy role contract requires explicit migration; stop and report it to Control',code='TASK_MIGRATION_REQUIRED')
    kind = packet.get('output_contract')
    expected_gate = {'kind':kind,
                     'command_suffix':DELIVERY_SUFFIX,
                     'required_before':['native_report','worker_done'],
                     'success':{'exit_code':0,'valid':True},
                     'failure_action':'correct_and_rerun_same_session',
                     'exact_bytes_required':True}
    gate = packet.get('delivery_validation', expected_gate)
    if not kind or gate != expected_gate:
        raise Rejected('packet delivery validation contract is missing or inconsistent')
    mats_launcher = (ROOT / 'bin' / ('mats.cmd' if os.name == 'nt' else 'mats')).resolve()
    launcher = f'"{mats_launcher.as_posix()}"'
    packet_path = (Path(packet['artifact_root']) / packet_ref['path']).resolve()
    delivery_path = (Path(packet['artifact_root']) / 'tmp' / 'deliveries' / f'{packet["id"]}.yaml').resolve()
    repo_path = Path(repo).resolve()
    delivery_command=f'{launcher} deliver "{packet["id"]}" --repo "{repo_path.as_posix()}"'
    return {
        'role':role,'role_path_text':role_path_text,'contract':contract,'launcher':launcher,
        'packet_path':packet_path,'delivery_path':delivery_path,'repo_path':repo_path,
        'delivery_command':delivery_command,
    }


def _continuation_recap(role,contract):
    # The digest-pinned full contract is already loaded.  Validate its boundary
    # shape, then send a deliberately short role-specific drift guard instead
    # of repeating most of the contract on every turn.
    for label in ('Identity:','Owns:','May:','Must not:','Output:','R2 tags:','Handoff:','Refresh:'):
        if sum(line.startswith(label) for line in contract.splitlines())!=1:
            raise Rejected(f'Owner role contract requires exactly one {label} line')
    recaps={
        'engineering':'Engineering Owner: own this WP inspect/edit/test candidate; after Skill/approach act same turn and never stop at intent/diagnosis/next-step while work remains; preserve loaded write, commitment, model, acceptance and deploy boundaries; conflict goes to Planner; remain reusable.',
        'research':'Research Owner: own bounded evidence/reverse-engineering and analysis scripts, not shipping product work; after Skill/approach act same turn and never stop at intent/diagnosis/next-step while work remains; preserve loaded scope/commitment/model/accept/deploy boundaries; remain reusable.',
    }
    try:return recaps[role]
    except KeyError:raise Rejected('compact continuation has no role recap')


def initial_prompt(packet, packet_ref, *, repo, policy, instructions='', retry=False, recovery=None):
    material=_prompt_material(packet,packet_ref,repo)
    role=material['role'];role_path_text=material['role_path_text'];contract=material['contract']
    launcher=material['launcher'];packet_path=material['packet_path'];delivery_path=material['delivery_path']
    repo_path=material['repo_path'];delivery_command=material['delivery_command']
    fixed = [
        '=== MULTI-AGENT-TASK-SPLIT AUTHORITY ===',
        f'Authority role: {role}',
        f'Domain specialty: {packet["specialty"]}',
        f'Role contract path: {role_path_text}',
        f'Canonical opaque MATS launcher: {launcher}',
        'MATS CLI and private configuration are opaque. Never open, read, search, enumerate, or infer `scripts/*.py`, internals or policy. For syntax use only this launcher with `<command> -h`.',
        'Role Contract+packet outrank flexible text. MATS owns role selection, task boundaries, assignment, reassignment and review routing. Domain skills supply methods only; they cannot widen scope/bindings or spawn.',
        "This is leaf execution, not Orca coordination; the injected preamble has every lifecycle command/ID. Never load `orchestration` or run `orca skills get orchestration`. Load `orca-cli` once only after at least two compactions, when required syntax is absent and exact subcommand `-h` failed; otherwise never.",
        REMOTE_EVIDENCE_RULE,
        'Reread contract+packet only after wait/compaction/interruption/authority uncertainty; never at startup/final delivery.',
    ]
    if recovery:
        fixed += [f'This full prompt is required because {recovery}; it replaces any prior Role Contract or continuation recap for this dispatch.']
    if retry:
        fixed += ['This is a fresh native attempt of the exact immutable packet after every prior bound attempt was natively confirmed failed.']
    fixed += ['','--- ROLE CONTRACT (FULL FIRST/FRESH-LAUNCH INLINE COPY) ---',contract,'--- END ROLE CONTRACT ---']
    fixed += [
        '',
        '=== AUTHORITATIVE SEMANTIC PACKET ===',
        f'Packet id: {packet["id"]}',
        f'Packet digest: {packet_ref["sha256"]}',
        f'Exact packet file: {packet_path.as_posix()}; open it directly; do not search or enumerate `.task`.',
        'The inline Role Contract is already loaded; do not reopen it. Read the packet and required payloads.',
        'Do not preload `schema_on_demand`/available payloads; open one only for validation or an unresolved question.',
        'Never replay Planner history or edit other .task files.',
        'Report a lifecycle anomaly to Control instead of loading coordinator guidance.',
        '',
        '=== PRE-DELIVERY MECHANICAL GATE ===',
        f'Fill the launcher-generated UTF-8 TSV semantic form at `{delivery_path.as_posix()}`. Keep its header/row names; this is the only `.task` path you may write. Then run `{delivery_command}`.',
        'Author semantic cells only. Evidence/Planner/Aux refs are paths; the gate materializes every identity, schema, version, hash, snapshot and binding reference, then replaces the form with canonical YAML. `scope.paths` limits writes; read paths are advice and need no grant.',
        'Missing transaction fields, including the current workspace snapshot, are expected and never a blocked/failed condition; only the gate computes them.',
        'Before the gate, stop owned background processes and close/flush every workspace/evidence handle. After it passes, do not mutate workspace or evidence.',
        'Only exit 0 with `valid: true` permits delivery. On failure, correct it and rerun this gate in the same session; never ask about MATS mechanics. If contradictory, escalate once without asking.',
        'Keep the finalized canonical file in place; edits require recheck. `worker_done.reportPath` is display-only and MATS ignores it. Use only injected or returned MATS operations.',
    ]
    if role in OWNERS:
        wait_command=f'{launcher} wait --actor-packet "{packet_ref["path"]}" --repo "{repo_path.as_posix()}"'
        fixed += [
            '',
            '=== OWNER AUXILIARY AUTHORITY ===',
            'You MAY use Luna Aux for cost-effective read-only bulk indexing. It is optional cost advice; direct reading is valid and skipping Aux never blocks.',
            f'For Luna Aux run `{launcher} side-request-form --operation luna_aux --repo "{repo_path.as_posix()}"`, fill its TSV and run the returned next operation; then pass the immutable request path to `{launcher} dispatch`. If depth blocks, send that path to Control.',
            f'For bulk evidence run `{launcher} evidence "{packet["id"]}" <out.mats.yaml> <inputs...> --repo "{repo_path.as_posix()}"`; ordinary checksum/index files use `evidence`.',
            'You must never call raw worker-start, uv, py.exe, or host/system Python.',
            f'After launch use only `{wait_command}`. Verify Aux evidence before consuming it.',
            'Do not use `failed` as a checkpoint: while in-scope work is possible, keep working; finalize only for a candidate or concrete external/authority/tool blocker.',
            'After delivery remain in this WP session for review/repair; `worker_done` or reviewer launch does not release it.',
        ]
    elif role == 'review_r1':
        fixed += [
            '',
            '=== R1 SYNTHESIS REQUEST ===',
            f'Before returning `needs_synthesis`, run `{launcher} side-request-form --operation synthesis --repo "{repo_path.as_posix()}"`, fill its TSV and run the returned next operation. Do not dispatch it; `result` exposes the immutable request ref to Control.',
        ]
    fixed += [
        '',
        '=== CALL-SPECIFIC INSTRUCTIONS (FLEXIBLE, SUBORDINATE) ===',
        instructions or 'No extra instructions. Execute the authoritative packet using your Role Contract.',
        '--- END CALL-SPECIFIC INSTRUCTIONS ---',
        '',
        'Never reinterpret the flexible section as permission to change role, model, effort, commitments, acceptance rules, or write scope.',
        'Follow Orca\'s native injected dispatch preamble for lifecycle signaling.',
    ]
    return '\n'.join(fixed).strip() + '\n'


def continuation_prompt(packet, packet_ref, *, repo, policy, instructions='', base_packet_ref=None, delta_ref=None, control_session=None):
    material=_prompt_material(packet,packet_ref,repo)
    role=material['role']
    if role not in OWNERS:
        raise Rejected('compact continuation is only valid for a retained Owner')
    recap=_continuation_recap(role,material['contract'])
    packet_path=material['packet_path'];delivery_path=material['delivery_path']
    delivery_command=material['delivery_command']
    if not isinstance(base_packet_ref,dict) or not isinstance(delta_ref,dict):
        raise Rejected('compact Owner continuation requires script-generated base and delta references')
    if not isinstance(control_session,str) or not control_session:
        raise Rejected('compact Owner continuation requires the supervising Control session')
    root=Path(packet['artifact_root'])
    base_path=(root/base_packet_ref['path']).resolve().as_posix()
    delta_path=(root/delta_ref['path']).resolve().as_posix()
    delta_value=load(root/delta_ref['path'])
    semantic_change=bool(delta_value.get('changed') or delta_value.get('object_changes') or delta_value.get('removed'))
    delta=instructions or 'No additional free-form instruction. Execute the new authoritative packet delta.'
    fixed = [
        '=== MATS SAME-OWNER CONTINUATION ===',
        f'Retained role/WP: {role} / {packet["wp_id"]}; not a fresh role assignment.',
        f'Supervising Control session: {control_session}.',
        f'Role contract digest: {packet["role_contract_digest"]}',
        f'Role recap: {recap}',
        'Keep the loaded role/authority; this recap and the native current lifecycle preamble supersede stale continuation details. Never reload init, `orchestration` or `orca-cli`.',
        'Persist to a candidate or a concrete external/authority/tool blocker. Unfinished, large or multi-step work is not `failed` and not a checkpoint; keep working instead of finalizing or sending `worker_done`.',
        'After loading a required Skill or announcing an approach, immediately execute the concrete work in this same turn; never end with only intent, diagnosis or a next-step description.',
        'If required remote evidence cannot be obtained, request the exact missing item through the appended route.',
        '',
        '=== CURRENT INPUT ===',
        f'Packet: {packet["id"]} / {packet_ref["sha256"]}.',
    ]
    if semantic_change:
        fixed += [f'Base already loaded: {base_path}. Open only semantic delta `{delta_path}`; its changes/removals are the complete packet update.']
    else:
        fixed += ['Packet semantics are unchanged from the loaded base; do not open the empty delta or full packet.']
    fixed += [
        f'Full packet `{packet_path.as_posix()}` is recovery-only after compaction, interruption or authority uncertainty; never search `.task` or replay Planner history.',
        '',
        'Instructions (verbatim, subordinate):',
        delta,
        '',
        '=== DELIVERY ===',
        f'Fill only the launcher-generated semantic TSV form at `{delivery_path.as_posix()}`, then run `{delivery_command}`.',
        'Write semantic cells/paths only; MATS generates transaction data. Stop owned processes and close/flush handles first. Only exit 0 with `valid: true` permits one `worker_done`; mutate nothing afterward. Correct the same form on failure; report one missing/contradictory public path without reading scripts.',
    ]
    return '\n'.join(fixed).strip() + '\n'


def continuation_route(*,run_id,task_id,dispatch_id,terminal,control_session):
    """Small lifecycle appendix for an existing Owner session.

    The full Orca orchestration guide and first-launch authority are already in
    the session.  A continuation needs only its new lifecycle identity and the
    exact reporting/question commands.
    """
    return '\n'.join([
        '=== ORCA CONTINUATION ROUTE ===',
        f'Run/task/dispatch: {run_id} / {task_id} / {dispatch_id}.',
        f'Supervising Control session: {control_session}.',
        'This is the current supervised turn; these IDs supersede every stale lifecycle ID.',
        'After the MATS delivery gate returns exit 0 with valid: true, report exactly once with:',
        f'`orca orchestration send --run {run_id} --from {terminal} --subject "MATS worker_done" --body "<three concise sentences: work, finding, remaining>" --type worker_done --task-id {task_id} --dispatch-id {dispatch_id} --outcome succeeded --files-modified "<comma-separated paths or empty>" --json`',
        'If exact remote evidence is unavailable, ask for only that evidence with:',
        f'`orca orchestration ask --from {terminal} --question "<exact missing evidence>" --timeout-ms 600000 --json`',
        'For an unrecoverable public-tool/authority contradiction, send one escalation with the current task/dispatch IDs. Do not load orchestration or orca-cli.',
    ])


def _effective(start):
    try:
        return normalize_effective(start['result']['launch']['effective'])
    except (KeyError, TypeError):
        raise Rejected('worker-start receipt lacks launch.effective; binding is unverified')


def _dispatch_id(start):
    try:
        result=start['result'];dispatch=result.get('dispatch') or {}
        return result.get('dispatchId') or result.get('dispatch_id') or dispatch.get('id') or dispatch.get('dispatchId') or dispatch.get('dispatch_id')
    except (KeyError, TypeError,AttributeError):
        return None


def public_dispatch_result(value):
    """Project only state-machine inputs; keep policy/prompts/raw receipts private."""
    keys=('executed','operation','role','retry','packet_ref','task_id','dispatch_id','binding_ref')
    out={k:value[k] for k in keys if k in value}
    if value.get('fallback_used'):out['model_fallback_attested']=True
    if not value.get('executed') and value.get('admission') is not None:out['admission']=value['admission']
    return out


def _current_owner_continuation(g,wp):
    if not wp: raise Rejected('--continue-owner requires --wp')
    state=g.state();source_ref=state['current_candidates'].get(wp) or state['latest_sources'].get(wp)
    if not source_ref: raise Rejected('same-WP continuation requires a current candidate or latest Owner result')
    source=g.files.get(source_ref);binding=g.files.get(source['binding_ref']);packet=g.files.get(binding['packet_ref'])
    if binding['role'] not in OWNERS or packet['wp_id']!=wp:
        raise Rejected('current/latest source is not backed by a same-WP Owner binding')
    g.resume_anchor(binding['packet_ref'])
    return binding['receipt'],bool(packet.get('cyber',False)),binding['packet_ref']


def _task_packet_identity(spec):
    if not isinstance(spec,str):return None
    patterns=(
        r'(?:^|\n)Packet id: (p\d{6})(?:\r?\n)Packet digest: ([0-9a-f]{64})(?:\r?\n|$)',
        r'(?:^|\n)Packet: (p\d{6}) / ([0-9a-f]{64})\.(?:\r?\n|$)',
    )
    found=[]
    for pattern in patterns:found.extend(re.findall(pattern,spec))
    unique=list(dict.fromkeys(found))
    return unique[0] if len(unique)==1 else None


def _continuation_task(task,wp,control_session):
    spec=task.get('spec')
    return (isinstance(spec,str) and '=== MATS SAME-OWNER CONTINUATION ===' in spec and
            f'Retained role/WP: ' in spec and f' / {wp};' in spec and
            f'Supervising Control session: {control_session}.' in spec)


def _verified_owner_show(shown,*,run_id,task_id,dispatch_id,reuse_receipt):
    native=shown.get('result') or {};dispatch=native.get('dispatch') or {};terminal=native.get('terminal') or {}
    valid=(_pick_id(dispatch,'id','dispatch_id','dispatchId')==dispatch_id and
           _pick_id(dispatch,'task_id','taskId')==task_id and
           _pick_id(dispatch,'run_id','runId')==run_id and
           _pick_id(terminal,'codexSessionId','codex_session_id','agentSessionId','agent_session_id',
                    'sessionId','session_id','incarnationId','incarnation_id')==reuse_receipt['session_id'] and
           _pick_id(terminal,'worktreeId','worktree_id')==reuse_receipt['workspace_key'] and
           terminal.get('connected') is True and terminal.get('writable') is True)
    if not valid:
        raise Rejected('native continuation does not attest the retained Owner session and placement',
                       code='OWNER_REBIND_IDENTITY_UNVERIFIED')
    return native


def _deliver_continuation(cli,terminal,prompt,*,run_id,task_id,dispatch_id,control_session):
    routed=prompt.rstrip()+"\n\n"+continuation_route(run_id=run_id,task_id=task_id,
            dispatch_id=dispatch_id,terminal=terminal,control_session=control_session)+"\n"
    delivery=terminal_send(cli,terminal,routed)
    submit=terminal_submit(cli,terminal)
    return delivery,submit


def _recover_unbound_owner_dispatch(g,cli,wp,reuse_receipt,control_session):
    """Reconcile and resume one exact MATS continuation without fresh task IO."""
    bound={(binding['packet_ref']['path'],binding['packet_ref']['sha256'])
           for _ref,binding in g.files.all('bindings')}
    current_version=g.state()['plan']['version']
    packets=[(ref,packet) for ref,packet in g.files.all('packets')
             if (ref['path'],ref['sha256']) not in bound and packet.get('wp_id')==wp and packet.get('role') in OWNERS and
                packet.get('plan_version')==current_version]
    if not packets:return None
    ensure_run_context(cli,g.state()['run_id'])
    terminal_handle,terminal_proof=retained_terminal_handle(cli,reuse_receipt)
    run_id=g.state()['run_id']
    ready,ready_receipt=tasks_with_status(cli,run_id,'ready')
    dispatched,dispatched_receipt=tasks_with_status(cli,run_id,'dispatched')
    packet_map={(packet['id'],pref['sha256']):(pref,packet) for pref,packet in packets}
    ready_matches=[];dispatched_matches=[];stale=[];stale_ready=[]
    for task in ready+dispatched:
        if not _continuation_task(task,wp,control_session):continue
        identity=_task_packet_identity(task.get('spec'))
        match=packet_map.get(identity)
        if match:
            row=(*match,task)
            (dispatched_matches if task.get('status')=='dispatched' else ready_matches).append(row)
        elif task.get('status')=='dispatched':stale.append(task)
        else:stale_ready.append(task)
    # A MATS context-only dispatch whose immutable packet disappeared or was
    # replaced cannot be executed. Fence only that unsupervised idle dispatch;
    # worker-stop retains its pre-existing terminal.
    stale_receipts=[]
    for task in stale:
        did=task.get('dispatch_id')
        if not isinstance(did,str):continue
        shown=worker_show(cli,did);native=_verified_owner_show(shown,run_id=run_id,
                task_id=task['id'],dispatch_id=did,reuse_receipt=reuse_receipt)
        worker=native.get('worker') or {};terminal=native.get('terminal') or {}
        if worker.get('state')!='unsupervised' or worker.get('stage')!='context_only' or not isinstance(terminal.get('agentWait'),dict):
            raise Rejected('stale unbound continuation may have executed; automatic fencing is unsafe',
                           code='OWNER_STALE_DISPATCH_ACTIVE')
        stale_receipts.append(stop_worker(cli,did))
    if len(dispatched_matches)>1:
        raise Rejected('multiple exact unbound Owner dispatches match current immutable packets',
                       code='OWNER_REBIND_RECOVERY_AMBIGUOUS')
    candidates=dispatched_matches or ready_matches
    if not candidates:return None
    candidates.sort(key=lambda row:int(row[1]['id'][1:]))
    pref,packet,task=candidates[-1]
    # Old ready retries are pure orchestration debris. Settle them before the
    # latest exact retry so the next continuation cannot regress to one.
    superseded=[]
    for old_task in stale_ready:
        superseded.append(fail_task(cli,old_task['id'],run_id,reason='immutable packet no longer exists'))
    for _old_pref,_old_packet,old_task in ready_matches:
        if old_task['id']!=task['id']:
            superseded.append(fail_task(cli,old_task['id'],run_id,reason=f'superseded by {task["id"]}'))
    runtime_view,_runtime_path=capture_runtime_view(g,cli)
    runtime_view=_runtime_with_rebound_owner(runtime_view,reuse_receipt,wp)
    g.preflight(pref,runtime_view,reuse_receipt['workspace_key'],reuse_receipt['access'],
                reuse_session=reuse_receipt['session_id'],require_failed_retry=False)
    delivery_path=g.files.delivery_path(packet['id'],create=True)
    if not delivery_path.exists():atomic_write(delivery_path,render_form(hydrate(g.files,pref)))
    if dispatched_matches:
        did=task['dispatch_id'];shown=worker_show(cli,did)
        native=_verified_owner_show(shown,run_id=run_id,task_id=task['id'],dispatch_id=did,reuse_receipt=reuse_receipt)
        start={'ok':True,'result':{'dispatch':native['dispatch']},
               '_mats_same_terminal_recovery':{'mode':'adopt_session_bound_dispatch'}}
        worker=native.get('worker') or {};terminal=native.get('terminal') or {}
        if worker.get('stage')=='context_only' and isinstance(terminal.get('agentWait'),dict):
            delivery,submit=_deliver_continuation(cli,terminal_handle,task['spec'],run_id=run_id,
                    task_id=task['id'],dispatch_id=did,control_session=control_session)
        else:
            delivery={'ok':True,'result':{'skipped':'native dispatch is already executing'}}
            submit={'ok':True,'result':{'skipped':'native dispatch is already executing'}}
    else:
        start=dispatch_context_task(cli,task['id'],terminal_handle,run_id)
        did=_dispatch_id(start)
        if not did:raise Rejected('native context dispatch lacks dispatchId')
        shown=worker_show(cli,did)
        _verified_owner_show(shown,run_id=run_id,task_id=task['id'],dispatch_id=did,reuse_receipt=reuse_receipt)
        delivery,submit=_deliver_continuation(cli,terminal_handle,task['spec'],run_id=run_id,
                task_id=task['id'],dispatch_id=did,control_session=control_session)
    canonical=normalize_launch_receipt(start,shown,packet_digest=pref['sha256'],access=reuse_receipt['access'],
            fresh_context=False,effective=reuse_receipt['effective'],simulation=g.state()['simulation'],
            model_fallback=reuse_receipt.get('model_fallback'),
            source='MATS reconciled exact unbound same-session continuation')
    binding_ref=g.bind(pref,canonical)
    return {'executed':True,'operation':'owner','role':packet['role'],'retry':False,'packet_ref':pref,
            'task_id':task['id'],'dispatch_id':did,'binding_ref':binding_ref,'fallback_used':False,
            'canonical_launch_receipt':canonical,'native_task_receipt':ready_receipt,
            'native_worker_show_receipt':shown,'native_owner_probe_receipt':terminal_proof,
            'native_delivery_receipt':delivery,'native_submit_receipt':submit,
            'native_recovery':{'reason':'reconciled_unbound_session_task','session_id':reuse_receipt['session_id'],
                               'stale_dispatches_fenced':len(stale_receipts),'ready_tasks_superseded':len(superseded)}}


def _pick_id(value,*keys):
    for key in keys:
        if isinstance(value,dict) and isinstance(value.get(key),str) and value[key]:return value[key]
    return None


def _runtime_with_rebound_owner(view,receipt,wp):
    """Add one session-proved Owner to an otherwise dispatch-derived view."""
    users=list(view['workspace_users'])
    matches=[u for u in users if u['session_id']==receipt['session_id']]
    expected={'session_id':receipt['session_id'],'workspace_key':receipt['workspace_key'],
              'access':receipt['access'],'wp_id':wp}
    if matches and any(u!=expected for u in matches):
        raise Rejected('runtime view conflicts with the rebound Codex session placement',
                       code='OWNER_SESSION_PLACEMENT_UNVERIFIED')
    if not matches:users.append(expected)
    return {**view,'workspace_users':sorted(users,key=lambda x:x['session_id'])}


def _control_session(g):
    state=g.state();ref=state.get('control_ref')
    if not isinstance(ref,dict):
        raise Rejected('Owner continuation requires an attached Control session')
    receipt=g.files.get(ref);session=receipt.get('session_id')
    if not isinstance(session,str) or not session:
        raise Rejected('attached Control receipt lacks its session identity')
    return session


def _packet_access(g,packet):
    if packet['role'] not in OWNERS:return 'read_snapshot'
    work=next((item for item in g.state()['plan']['work_packages'] if item['id']==packet['wp_id']),None)
    if work is None:raise Rejected('packet WP is absent from the current plan')
    return 'write' if work['scope']['paths'] else 'read_snapshot'


def _prior_packet_receipt(g,packet_ref):
    receipts=[binding['receipt'] for _ref,binding in g.files.all('bindings') if binding['packet_ref']==packet_ref]
    if not receipts:raise Rejected('packet retry requires a prior bound dispatch')
    placement={(r['workspace_key'],r['workspace_path'],r['access']) for r in receipts}
    if len(placement)!=1:raise Rejected('packet retry bindings disagree on their original placement')
    return receipts[-1]


def spawn(g, *, name=None, operation=None, wp=None, request=None, worktree='current', cli='orca', instructions='', terminal=None, reuse_receipt=None, continue_owner=False, runtime_view=None, workspace_key=None, access=None, cyber=False, retry_packet=None, dry_run=False):
    managed_owner_continuation=bool(continue_owner)
    retained_owner_probe=None
    prior_owner_packet_ref=None
    retry = retry_packet is not None
    if retry:
        if any((name is not None, operation is not None, wp is not None, request is not None,
                bool(instructions), terminal is not None, reuse_receipt is not None, continue_owner, cyber)):
            raise Rejected('packet retry forbids fresh name/operation/wp/request/instructions/continuation/cyber overrides')
        try: g.files.control_path(retry_packet['path'],prefixes=('packets',))
        except (KeyError,TypeError): raise Rejected('packet retry requires a path+sha256 internal reference')
        pref = retry_packet
        packet = g.files.get(pref)
        operation = 'owner' if packet['role'] in OWNERS else packet['role']
        wp = packet.get('wp_id')
        cyber = bool(packet.get('cyber',False))
    else:
        if not operation:
            raise Rejected('fresh dispatch requires --operation')
        name=name or g.files.next_index('packets')
        if bool(terminal) != bool(reuse_receipt):
            raise Rejected('same-owner continuation requires both terminal and reuse receipt')
        if continue_owner:
            if operation!='owner' or terminal is not None or reuse_receipt is not None:
                raise Rejected('--continue-owner is only for owner and replaces manual terminal/reuse receipt')
            reuse_receipt,cyber,prior_owner_packet_ref=_current_owner_continuation(g,wp)
            terminal='<retained-owner-terminal>'
            if not dry_run:
                recovery_control_session=_control_session(g)
                with g.files.lock():
                    recovered=_recover_unbound_owner_dispatch(g,cli,wp,reuse_receipt,
                            recovery_control_session)
                if recovered is not None:return recovered
        request_obj = _request_argument(g,operation,request)
        pref = g.issue(name, operation, wp_id=wp, request=request_obj, cyber=cyber)
        packet = g.files.get(pref)
    hydrated_packet=hydrate(g.files,pref)
    delivery_prefill=None
    if packet['role']=='planner' and packet.get('request',{}).get('repair_of'):
        feedback=hydrated_packet.get('planner_repair_feedback')
        if not isinstance(feedback,dict) or not isinstance(feedback.get('rejected_result_ref'),dict):
            raise Rejected('Planner repair packet lacks its exact rejected-result prefill')
        delivery_prefill=g.files.get(feedback['rejected_result_ref'])
    # Render early so malformed packet/form semantics fail before native work, but
    # do not touch the attempt's delivery until admission has succeeded.  In
    # particular, a rejected retry must preserve the prior attempt byte-for-byte.
    delivery_path=g.files.delivery_path(packet['id'])
    delivery_form=render_form(hydrated_packet,prefill=delivery_prefill)
    continuation = terminal is not None
    prior_receipt=reuse_receipt if reuse_receipt is not None else _prior_packet_receipt(g,pref) if retry else None
    inferred_access=prior_receipt['access'] if prior_receipt else _packet_access(g,packet)
    if access is not None and access!=inferred_access:
        raise Rejected(f'access is launcher-owned for this packet: expected {inferred_access}')
    access=inferred_access
    if prior_receipt:
        if workspace_key is not None and workspace_key!=prior_receipt['workspace_key']:
            raise Rejected('continuation/retry must keep the attested workspace identity')
        workspace_key=prior_receipt['workspace_key']
        if retry and worktree=='current':worktree=workspace_key
    native_recovery=None
    if dry_run and managed_owner_continuation and runtime_view is not None:
        retained=any(u['session_id']==reuse_receipt['session_id'] for u in runtime_view['workspace_users'])
        if not retained:
            terminal=None;continuation=False
            native_recovery={'reason':'retained_owner_absent','replaced_dispatch_id':reuse_receipt['dispatch_id']}
    # A proved same-session continuation is never converted back into a full
    # first-launch prompt.  A Skill update changes the pinned digest and the
    # script-generated recap/delta, not the already-running agent's identity.
    compact_continuation=bool(managed_owner_continuation and continuation)
    control_session=_control_session(g) if continuation else None
    delta_ref=None
    if compact_continuation:
        delta_value=continuation_delta(g.files,prior_owner_packet_ref,pref)
        delta_ref=g.files.put('payloads','owner-continuation-'+digest(delta_value),delta_value)
        prompt=continuation_prompt(packet,pref,repo=g.files.repo,policy=g.policy(),instructions=instructions,
                                   base_packet_ref=prior_owner_packet_ref,delta_ref=delta_ref,control_session=control_session)
        prompt_mode='compact_continuation'
    else:
        recovery=None
        if managed_owner_continuation:
            recovery='the retained Owner was absent'
        prompt=initial_prompt(packet,pref,repo=g.files.repo,policy=g.policy(),instructions=instructions,retry=retry,recovery=recovery)
        prompt_mode='full'
    bindings = dispatch_bindings(g.policy(), packet['role'], cyber=cyber)
    expected = bindings['primary']
    fallback_binding = bindings['fallback']
    admission = None
    if runtime_view is not None and dry_run:
        if not workspace_key:workspace_key='dry-run/current'
        reuse_session=(reuse_receipt or {}).get('session_id') if continuation else None
        admission = g.preflight(pref, runtime_view, workspace_key, access, reuse_session=reuse_session,require_failed_retry=retry)
    preview = {
        'operation': operation,
        'role': packet['role'],
        'retry': retry,
        'cyber': cyber,
        'expected_binding': expected,
        'fallback_binding': fallback_binding,
        'role_contract_path': (ROOT/'references/roles'/f"{packet['role']}.md").resolve().as_posix(),
        'packet_ref': pref,
        'continuation_delta_ref': delta_ref,
        'prompt': prompt,
        'prompt_mode': prompt_mode,
        'task_create_argv': [cli,'orchestration','task-create','--spec','<generated-initial-prompt>','--json'],
        'worker_start_argv': launch_argv(g.policy(), packet['role'], '<task_id>', worktree, cli=cli,
                terminal=terminal if continuation else None,reuse_receipt=reuse_receipt if continuation else None,cyber=cyber),
        'worker_start_fallback_argv': launch_argv(g.policy(), packet['role'], '<task_id>', worktree, cli=cli, cyber=cyber, fallback=True) if fallback_binding and not continuation else None,
        'admission': admission,
        'native_recovery': native_recovery,
        'executed': False,
    }
    if dry_run:
        delivery_path=g.files.delivery_path(packet['id'],create=True)
        atomic_write(delivery_path,delivery_form)
        return preview
    with g.files.lock():
        if runtime_view is None:
            runtime_view,_runtime_path=capture_runtime_view(g,cli)
        if workspace_key is None:
            workspace_key=resolve_workspace_key(cli,g.files.repo,worktree)
        if managed_owner_continuation:
            try:
                terminal,retained_owner_probe=retained_terminal_handle(cli,reuse_receipt)
                retained=True
            except Rejected as exc:
                if exc.code!='OWNER_SESSION_NOT_FOUND':raise
                retained=False
            if retained:
                runtime_view=_runtime_with_rebound_owner(runtime_view,reuse_receipt,wp)
                admission=g.preflight(pref,runtime_view,workspace_key,access,reuse_session=reuse_receipt['session_id'],require_failed_retry=False)
            else:
                runtime_view={**runtime_view,'workspace_users':[u for u in runtime_view['workspace_users']
                    if u['session_id']!=reuse_receipt['session_id']]}
                admission=g.preflight(pref,runtime_view,workspace_key,access,reuse_session=None,require_failed_retry=False)
                terminal=None;continuation=False
                control_session=None
                native_recovery={'reason':'retained_owner_absent','replaced_dispatch_id':reuse_receipt['dispatch_id']}
                prompt=initial_prompt(packet,pref,repo=g.files.repo,policy=g.policy(),instructions=instructions,
                                      recovery='the retained Owner was absent')
                prompt_mode='full'
        else:
            admission = g.preflight(pref, runtime_view, workspace_key, access, reuse_session=(reuse_receipt or {}).get('session_id'),require_failed_retry=retry)
        preview['admission']=admission;preview['prompt']=prompt;preview['prompt_mode']=prompt_mode
        preview['worker_start_argv']=launch_argv(g.policy(),packet['role'],'<task_id>',worktree,cli=cli,
                terminal=terminal if continuation else None,reuse_receipt=reuse_receipt if continuation else None,cyber=cyber)
        delivery_path=g.files.delivery_path(packet['id'],create=True)
        atomic_write(delivery_path,delivery_form)
        run_context = ensure_run_context(cli, g.state()['run_id'])
        task = create_task(cli,prompt)
        try:
            task_id = task['result']['task']['id']
        except (KeyError, TypeError):
            raise Rejected('task-create receipt lacks result.task.id')
        if continuation:
            # Existing Owner sessions are addressed by session identity, not
            # Orca's optional recognized-agent launcher metadata.  A plain
            # context dispatch supplies lifecycle authority; MATS sends the
            # compact delta itself and confirms the composer with pure Enter.
            start=dispatch_context_task(cli,task_id,terminal,g.state()['run_id'])
            did=_dispatch_id(start)
            if not did:raise Rejected('native context dispatch lacks dispatchId')
            shown=worker_show(cli,did)
            _verified_owner_show(shown,run_id=g.state()['run_id'],task_id=task_id,
                                 dispatch_id=did,reuse_receipt=reuse_receipt)
            delivery,submit=_deliver_continuation(cli,terminal,prompt,run_id=g.state()['run_id'],
                    task_id=task_id,dispatch_id=did,control_session=control_session)
            delivery_mode='session_index_context_dispatch_plus_prompt_and_enter'
            native_recovery={'reason':'same_session_native_dispatch',
                             'retained_dispatch_id':reuse_receipt['dispatch_id'],
                             'session_id':reuse_receipt['session_id'],
                             'terminal':terminal,
                             'terminal_reacquired':True,
                             'delivery_mode':delivery_mode}
        else:
            argv = launch_argv(g.policy(), packet['role'], task_id, worktree, cli=cli, cyber=cyber)
            fallback_argv = launch_argv(g.policy(), packet['role'], task_id, worktree, cli=cli, cyber=cyber, fallback=True) if fallback_binding else None
            start = start_worker(argv,fallback_argv=fallback_argv) if fallback_argv else start_worker(argv)
        fallback_used=bool((start.get('_mats_model_fallback') or {}).get('used'))
        actual_expected=fallback_binding if fallback_used else expected
        effective = reuse_receipt['effective'] if continuation else _effective(start)
        did = _dispatch_id(start)
        if effective != actual_expected:
            stop = None
            if did and not continuation:
                try: stop = stop_worker(cli,did)
                except Exception as e: stop = {'stop_error': str(e)}
            raise Rejected(f'ROLE_BINDING_UNVERIFIED expected={actual_expected} effective={effective} dispatch={did} stop={stop}')
        if not did: raise Rejected('worker-start receipt lacks dispatchId')
        if not continuation:shown=worker_show(cli,did)
        canonical=normalize_launch_receipt(start,shown,packet_digest=pref['sha256'],access=access,fresh_context=not continuation,effective=effective,
                                           model_fallback=start.get('_mats_model_fallback'),simulation=g.state()['simulation'],
                                           source='MATS normalized native same-session continuation + worker-show' if continuation else None)
        if canonical['workspace_key']!=workspace_key:
            if not continuation:
                try:stop_worker(cli,did)
                except Exception:pass
            raise Rejected(f'native launch used another workspace: expected={workspace_key} actual={canonical["workspace_key"]}')
        if continuation and canonical['session_id']!=reuse_receipt['session_id']:
            raise Rejected(f'owner continuation changed native session identity: expected={reuse_receipt["session_id"]} actual={canonical["session_id"]}')
        try:
            binding_ref=g.bind(pref,canonical)
        except Exception:
            if not continuation:
                try: stop_worker(cli,did)
                except Exception: pass
            raise
    return {
        **preview,
        'executed': True,
        'run_context': run_context,
        'task_id': task_id,
        'dispatch_id': did,
        'fallback_used': fallback_used,
        'binding_ref': binding_ref,
        'canonical_launch_receipt': canonical,
        'native_task_receipt': task,
        'native_start_receipt': start,
        'native_delivery_receipt': delivery if continuation else None,
        'native_submit_receipt': submit if continuation else None,
        'native_worker_show_receipt': shown,
        'native_owner_probe_receipt': retained_owner_probe,
        'native_recovery': native_recovery,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--repo', default='.')
    ap.add_argument('--name', help=argparse.SUPPRESS)
    ap.add_argument('--operation', choices=['owner','luna_aux','synthesis','review_r1','review_r2','planner'],help='fresh dispatch: semantic operation')
    ap.add_argument('--wp')
    ap.add_argument('--request', help='immutable MATS request path under .task; side/planner operations only')
    ap.add_argument('--worktree', default='current',help=argparse.SUPPRESS)
    ap.add_argument('--cli', default='orca',help=argparse.SUPPRESS)
    ap.add_argument('--instructions-file', help=argparse.SUPPRESS)
    ap.add_argument('--instructions',help='subordinate in-scope instructions/evidence paths; with --continue-owner this is local steering, not a plan change')
    ap.add_argument('--continue-owner',action='store_true',help='reuse the retained same-WP Owner for local steering or R0/R1/R2 repair')
    ap.add_argument('--runtime-view', help=argparse.SUPPRESS)
    ap.add_argument('--workspace-key', help=argparse.SUPPRESS)
    ap.add_argument('--access', choices=['write','read_live','read_snapshot'],help=argparse.SUPPRESS)
    ap.add_argument('--retry-packet',help=argparse.SUPPRESS)
    ap.add_argument('--retry-sha256',help=argparse.SUPPRESS)
    ap.add_argument('-cyber','--cyber',action='store_true',help='Control-classified cybersecurity task; replaces Sol with daybreak-blue when applicable')
    ap.add_argument('--dry-run', action='store_true',help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    try:
        g = Guards(a.repo)
        if bool(a.retry_packet) != bool(a.retry_sha256):
            raise Rejected('use --retry-packet and --retry-sha256 together')
        if a.retry_packet and any((a.name is not None,a.operation is not None,a.wp is not None,a.request is not None,
                                   a.instructions_file is not None,a.instructions is not None,a.continue_owner,a.cyber)):
            raise Rejected('packet retry forbids fresh semantic or continuation arguments')
        retry_ref=None
        if a.retry_packet:
            retry_path=g.files.control_path(a.retry_packet,prefixes=('packets',))
            retry_ref={'path':logical_relative(g.files.root,retry_path),'sha256':a.retry_sha256}
        extra = _instructions(g, a.instructions_file, a.instructions)
        rv = g.files.load_control(a.runtime_view,prefixes=('tmp',)) if a.runtime_view else None
        out = spawn(g, name=a.name, operation=a.operation, wp=a.wp, request=a.request, worktree=a.worktree,
                    cli=a.cli, instructions=extra, continue_owner=a.continue_owner, runtime_view=rv,
                    workspace_key=a.workspace_key, access=a.access, cyber=a.cyber, retry_packet=retry_ref,dry_run=a.dry_run)
        emit_utf8(public_dispatch_result(out))
        return 0
    except (Rejected, ValueError, KeyError, TypeError, OSError) as e:
        emit_utf8(rejection_payload(e),error=True)
        return 2


if __name__ == '__main__':
    try: require_managed_runtime()
    except RuntimeError as exc:
        emit_utf8(str(exc),error=True);raise SystemExit(126)
    raise SystemExit(main())
