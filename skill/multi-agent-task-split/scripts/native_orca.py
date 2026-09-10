"""Thin mechanical Orca CLI bridge.

All host/Orca compatibility is normalized here. Semantic code never consumes raw
Orca text encodings or raw provider field names.
"""
from __future__ import annotations
import json
import locale
import os
import subprocess
import time
from pathlib import Path
from common import Rejected, atomic_write, encode, identifier, load


class AgentUnconfigured(Rejected):
    """Exact native signal that a retained terminal cannot host another dispatch."""

    def __init__(self, error):
        self.error=error
        super().__init__(f'native retained Owner terminal is not a configured agent: {error}')


def _decode_bytes(data: bytes | None) -> str:
    if not data:
        return ''
    # Orca normally emits UTF-8. Packaged Windows launchers may inherit an OEM/ANSI
    # code page; accept that at the host boundary only. Semantic files remain UTF-8.
    encs=['utf-8-sig']
    pref=locale.getpreferredencoding(False)
    if pref: encs.append(pref)
    encs += ['gb18030','cp936']
    seen=set()
    for enc in encs:
        key=enc.lower()
        if key in seen: continue
        seen.add(key)
        try: return data.decode(enc)
        except (UnicodeDecodeError,LookupError): pass
    return data.decode('utf-8',errors='replace')


def _decode(cp, argv, *, allow_error=False):
    stdout=_decode_bytes(cp.stdout).strip()
    stderr=_decode_bytes(cp.stderr).strip()
    value=None
    if stdout:
        try:value=json.loads(stdout)
        except json.JSONDecodeError:
            if not allow_error or cp.returncode==0:
                raise Rejected(f"native command did not return one JSON document: {' '.join(argv[:3])}; output={stdout[:240]!r}")
    if value is None:
        value={'ok':False,'error':{'code':'native_process_error','message':(stderr or stdout).strip()},'_returncode':cp.returncode}
    # The structured Orca receipt is authoritative.  On Windows the terminal
    # bridge can successfully enqueue input and emit ``ok: true`` while its
    # wrapper exits non-zero (for example after a console/renderer warning).
    # Treating that transport exit as failure makes callers repeat a command
    # which has already taken effect.  Preserve the exit code for diagnostics,
    # but never turn an explicit successful receipt into an ambiguous failure.
    if cp.returncode and value.get('ok',False):
        value=dict(value);value['_returncode']=cp.returncode
    if not allow_error and not value.get('ok',False):
        raise Rejected(f"native command rejected: {value.get('error')}")
    return value


def run_json(argv, *, allow_error=False):
    try: cp=subprocess.run(argv,capture_output=True,text=False,shell=False)
    except OSError as e: raise Rejected(f"native command unavailable: {argv[0]}: {e}") from e
    return _decode(cp,argv,allow_error=allow_error)


def _runtime_ready(value):
    try:
        runtime=value['result']['runtime']
        return value.get('ok',False) and runtime.get('state')=='ready' and runtime.get('reachable') is True and runtime.get('connectionState')=='connected'
    except (KeyError,TypeError):
        return False


def ensure_runtime_ready(cli):
    """Return one ready status, starting Orca at most once when necessary."""
    status=run_json([cli,'status','--json'],allow_error=True)
    if _runtime_ready(status):return status
    opened=run_json([cli,'open','--json'],allow_error=True)
    if not opened.get('ok',False):
        raise Rejected(f"Orca runtime unavailable and automatic start failed: {opened.get('error')}")
    status=run_json([cli,'status','--json'],allow_error=True)
    if not _runtime_ready(status):
        state=(status.get('result') or {}).get('runtime') if isinstance(status,dict) else None
        raise Rejected(f'Orca runtime is not ready after one automatic start attempt: {state or status.get("error")}')
    return status


def _host_path(value):
    return os.path.normcase(os.path.normpath(str(Path(value).resolve())))


def resolve_workspace_key(cli,repo,worktree='current'):
    """Resolve current/an existing selector to Orca's authoritative worktree id."""
    repo=Path(repo).resolve()
    receipt=run_json([cli,'worktree','list','--repo',f'path:{repo.as_posix()}','--limit','100','--json'])
    result=receipt.get('result') or {};rows=result.get('worktrees')
    if not isinstance(rows,list) or result.get('truncated') is True:
        raise Rejected('Orca worktree inventory is incomplete')
    if worktree=='current':
        matches=[row for row in rows if isinstance(row,dict) and row.get('path') and _host_path(row['path'])==_host_path(repo)]
    else:
        selector=worktree[3:] if worktree.startswith('id:') else worktree
        matches=[row for row in rows if isinstance(row,dict) and selector in {row.get('id'),row.get('path'),row.get('displayName')}]
    if len(matches)!=1 or not isinstance(matches[0].get('id'),str) or not matches[0]['id']:
        raise Rejected(f'Orca cannot resolve worktree selector {worktree!r} uniquely inside the managed repository')
    return matches[0]['id']


def _confirmed_release(g,dispatch_id):
    """Return whether MATS already confirmed cleanup for this Dispatch."""
    path=g.files.lifecycle_operation_path('release',dispatch_id)
    if not path.is_file():return False
    expected={'schema_version':1,'kind':'release','native_id':dispatch_id,'confirmed':True}
    if load(path)!=expected:raise Rejected('conflicting release lifecycle operation record')
    return True


def _retained_owner_dispatches(g):
    state=g.state();dispatches=set()
    for ref in list(state.get('current_candidates',{}).values())+list(state.get('latest_sources',{}).values()):
        try:
            source=g.files.get(ref);binding=g.files.get(source['binding_ref'])
        except (KeyError,TypeError,Rejected):
            continue
        if binding.get('role') in {'research','engineering'}:
            dispatch_id=binding['receipt']['dispatch_id']
            if not _confirmed_release(g,dispatch_id):dispatches.add(dispatch_id)
    return dispatches


def capture_runtime_view(g,cli='orca',*,materialize=True):
    """Query Orca once; optionally materialize the compact admission view."""
    ready=ensure_runtime_ready(cli);state=g.state();run_id=state['run_id']
    receipt=run_json([cli,'orchestration','worker-list','--run',run_id,'--json'])
    result=receipt.get('result') or {};workers=result.get('workers')
    if not isinstance(workers,list):raise Rejected('Orca worker inventory is incomplete')
    if any(not isinstance(row,dict) or row.get('runId')!=run_id for row in workers):
        raise Rejected('Orca worker inventory contains a row from another Run')
    native={}
    for row in workers:
        if not isinstance(row,dict) or not isinstance(row.get('dispatchId'),str):
            raise Rejected('Orca worker inventory contains an invalid row')
        if row['dispatchId'] in native:raise Rejected('Orca worker inventory contains duplicate dispatch ids')
        native[row['dispatchId']]=row
    retained=_retained_owner_dispatches(g);active=[];users=[];settled=[]
    # Orca may expose the same live terminal as retained/external/user-takeover
    # after interactive inspection.  Those labels change native ownership, not
    # the process incarnation or MATS same-WP authority.
    terminal_states={'active','retained','reclaimable','release_pending','release_unknown',
                     'external','user-takeover','user_takeover'}
    outcome={'succeeded':'succeeded','failed':'failed'}
    for _ref,binding in g.files.all('bindings'):
        receipt_value=binding['receipt'];did=receipt_value['dispatch_id'];row=native.get(did)
        if row is None:continue
        packet=g.files.get(binding['packet_ref']);worker_state=row.get('workerState');terminal_state=row.get('terminalState')
        dispatch_status=row.get('dispatchStatus')
        # Non-injecting retained continuations stay ``workerState=unsupervised``
        # even after their Dispatch is completed. Dispatch status is therefore
        # the lifecycle authority when present; workerState is compatibility
        # fallback for older Orca inventories.
        if dispatch_status=='completed':is_active=False;settled_outcome='succeeded'
        elif dispatch_status in {'failed','stopped','abandoned','cancelled'}:is_active=False;settled_outcome='failed'
        elif dispatch_status in {'dispatched','running'}:is_active=True;settled_outcome=None
        else:
            is_active=worker_state not in {'succeeded','failed','stopped','abandoned'}
            settled_outcome=outcome.get(worker_state)
        if is_active:
            active.append({'dispatch_id':did,'wp_id':packet.get('wp_id'),'role':binding['role']})
        if settled_outcome is not None:
            settled.append({'dispatch_id':did,'outcome':settled_outcome})
        if terminal_state in terminal_states and (is_active or did in retained):
            users.append({'session_id':receipt_value['session_id'],'workspace_key':receipt_value['workspace_key'],
                          'access':receipt_value['access'],'wp_id':packet.get('wp_id')})
    runtime_id=((ready.get('_meta') or {}).get('runtimeId') or ((ready.get('result') or {}).get('runtime') or {}).get('runtimeId') or 'unknown')
    view={'project_id':state['project']['project_id'],'run_id':run_id,'complete':True,
          'source':f'MATS normalized Orca worker-list runtime={runtime_id}','simulation':state['simulation'],
          'active_dispatches':sorted(active,key=lambda x:x['dispatch_id']),
          'workspace_users':sorted(users,key=lambda x:x['session_id']),
          'settled_dispatches':sorted(settled,key=lambda x:x['dispatch_id'])}
    path=g.files.control_path('tmp/runtime-view.yaml')
    if materialize:atomic_write(path,encode(view))
    return view,path


def normalize_effective(raw):
    """Normalize Orca/provider launch.effective to the semantic binding shape."""
    if not isinstance(raw,dict): raise Rejected('native launch.effective is not an object')
    agent=raw.get('agent')
    if agent not in (None,'codex'):
        raise Rejected(f'unexpected native agent for managed Codex role: {agent}')
    model=raw.get('model')
    effort=raw.get('reasoning_effort', raw.get('effort'))
    if not isinstance(model,str) or not model.strip() or not isinstance(effort,str) or not effort.strip():
        raise Rejected(f'native launch.effective lacks model/effort: {raw}')
    return {'model':model,'reasoning_effort':effort}


def error_code(value):
    try:return value['error']['code']
    except (KeyError,TypeError):return None


def bound_run_id(task_list_receipt):
    try:return task_list_receipt['result']['runId']
    except (KeyError,TypeError):return None


def current_run_id(cli='orca'):
    """Return the caller's already-bound Orca Run without asking a model for it."""
    ensure_runtime_ready(cli)
    probe=run_json([cli,'orchestration','task-list','--brief','--json'],allow_error=True)
    if not probe.get('ok',False) and error_code(probe)=='invalid_argument':
        probe=run_json([cli,'orchestration','task-list','--json'],allow_error=True)
    if not probe.get('ok',False):
        raise Rejected(f"cannot derive the current Orca Run: {probe.get('error')}")
    run_id=bound_run_id(probe)
    if not isinstance(run_id,str) or not run_id:
        raise Rejected('task-list succeeded without authoritative runId')
    identifier(run_id)
    return run_id


def ensure_run_context(cli, expected_run_id):
    """Verify caller is on expected Run; bind only when native says no Run is bound."""
    probe=run_json([cli,'orchestration','task-list','--brief','--json'],allow_error=True)
    if not probe.get('ok',False) and error_code(probe)=='invalid_argument':
        probe=run_json([cli,'orchestration','task-list','--json'],allow_error=True)
    if probe.get('ok',False):
        actual=bound_run_id(probe)
        if actual and actual!=expected_run_id:
            raise Rejected(f'caller is bound to another Orca Run: expected={expected_run_id} actual={actual}')
        if not actual: raise Rejected('task-list succeeded without authoritative runId')
        return {'action':'already_bound','run_id':actual,'probe':probe}
    if error_code(probe)!='run_required':
        raise Rejected(f"cannot verify native Run context: {probe.get('error')}")
    used=run_json([cli,'orchestration','run-use','--id',expected_run_id,'--json'])
    check=run_json([cli,'orchestration','task-list','--json'])
    actual=bound_run_id(check)
    if actual!=expected_run_id:
        raise Rejected(f'run-use did not bind expected Run: expected={expected_run_id} actual={actual}')
    return {'action':'bound','run_id':actual,'run_use_receipt':used,'probe':check}


def create_task(cli, spec):
    return run_json([cli,'orchestration','task-create','--spec',spec,'--json'])


def _codex_session_id(value):
    """Return Orca's stable agent-session identity, never a terminal handle."""
    return _pick(value,'codexSessionId','codex_session_id','agentSessionId','agent_session_id',
                 'sessionId','session_id','incarnationId','incarnation_id')


def _live_codex_terminal(value, *, expected_session, expected_workspace=None):
    return (isinstance(value,dict) and isinstance(value.get('handle'),str) and bool(value['handle']) and
            _codex_session_id(value)==expected_session and
            (expected_workspace is None or _pick(value,'worktreeId','worktree_id')==expected_workspace) and
            value.get('connected') is True and value.get('writable') is True)


def _resolve_live_terminal(cli, terminal, *, expected_session, expected_workspace=None):
    """Resolve by Codex session only; handles/dispatches are replaceable metadata."""
    if not isinstance(expected_workspace,str) or not expected_workspace:
        raise Rejected('retained Codex session lacks its attested workspace placement',
                       code='OWNER_SESSION_PLACEMENT_UNVERIFIED')
    listed=run_json([cli,'terminal','list','--worktree',f'id:{expected_workspace}','--json'],allow_error=True)
    rows=((listed.get('result') or {}).get('terminals') if isinstance(listed,dict) else None)
    if not listed.get('ok',False) or not isinstance(rows,list):
        raise Rejected('cannot enumerate the retained Owner workspace for automatic session rebinding',
                       code='OWNER_SESSION_INDEX_UNAVAILABLE')
    matches=[row for row in rows if isinstance(row,dict) and _codex_session_id(row)==expected_session]
    if not matches:
        raise Rejected('the retained Codex session is absent from its workspace terminal inventory',
                       code='OWNER_SESSION_NOT_FOUND')
    if len(matches)!=1:
        raise Rejected('the Codex session identity is not unique in Orca terminal inventory',
                       code='OWNER_SESSION_INDEX_AMBIGUOUS')
    live=matches[0]
    if _pick(live,'worktreeId','worktree_id')!=expected_workspace:
        raise Rejected('the retained Codex session moved to another workspace',
                       code='OWNER_SESSION_PLACEMENT_UNVERIFIED')
    if not _live_codex_terminal(live,expected_session=expected_session,expected_workspace=expected_workspace):
        raise Rejected('the retained Codex session exists but is not connected and writable',
                       code='OWNER_SESSION_NOT_READY')
    old_handle=terminal if isinstance(terminal,str) and terminal else None
    return live,listed,old_handle!=live['handle']


def _model_unavailable(value):
    """Recognize only explicit model-availability failures, never general errors."""
    if not isinstance(value,dict): return False
    error=value.get('error') or {}
    if not isinstance(error,dict): return False
    code=str(error.get('code') or '').strip().lower().replace('-','_').replace(' ','_')
    if code in {'model_unavailable','model_not_available','model_not_found','unknown_model','unsupported_model','provider_model_unavailable'}:
        return True
    message=str(error.get('message') or '').strip().lower()
    return 'model' in message and any(marker in message for marker in ('unavailable','not available','not found','unknown','unsupported'))


def start_worker(argv, *, fallback_argv=None):
    if fallback_argv is None:
        primary=run_json(argv,allow_error=True)
        if isinstance(primary,dict) and primary.get('ok',False):
            return primary
        if error_code(primary)=='agent_unconfigured':
            raise AgentUnconfigured(primary.get('error'))
        detail=primary.get('error') if isinstance(primary,dict) else primary
        raise Rejected(f'native command rejected: {detail}')
    primary=run_json(argv,allow_error=True)
    if isinstance(primary,dict) and primary.get('ok',False):
        return primary
    if not _model_unavailable(primary):
        raise Rejected(f"native command rejected without eligible model fallback: {(primary or {}).get('error') if isinstance(primary,dict) else primary}")
    fallback=run_json(fallback_argv,allow_error=True)
    if not isinstance(fallback,dict) or not fallback.get('ok',False):
        detail=fallback.get('error') if isinstance(fallback,dict) else fallback
        raise Rejected(f'native Sol fallback rejected after primary model unavailable: {detail}')
    fallback=dict(fallback)
    fallback['_mats_model_fallback']={'used':True,'reason':'primary_model_unavailable','primary_error':primary.get('error')}
    return fallback
def stop_worker(cli, dispatch_id): return run_json([cli,'orchestration','worker-stop','--dispatch',dispatch_id,'--json'])
def release_worker(cli, dispatch_id):
    identifier(dispatch_id)
    receipt=run_json([cli,'orchestration','worker-release','--dispatch',dispatch_id,'--json'])
    result=receipt.get('result') or {}
    exact_release=result.get('state')=='released'
    no_owned_resource=(result.get('state')=='retained' and result.get('reason')=='no_owned_resource' and
                       result.get('processAction')=='none')
    if result.get('dispatchId')!=dispatch_id or not (exact_release or no_owned_resource):
        raise Rejected('native worker-release did not attest the requested released dispatch')
    return receipt
def worker_show(cli, dispatch_id):
    return run_json([cli,'orchestration','worker-show','--dispatch',dispatch_id,'--json'])


def inject_task(cli, task_id, terminal, run_id):
    """Fallback inject for an exact existing Codex session."""
    return run_json([cli,'orchestration','dispatch','--task',task_id,'--to',terminal,
                     '--run',run_id,'--inject','--json'])


def tasks_with_status(cli, run_id, status):
    """Return one bounded native task class for continuation reconciliation."""
    identifier(run_id)
    if status not in {'ready','dispatched'}:
        raise Rejected('unsupported native task inventory status')
    receipt=run_json([cli,'orchestration','task-list','--run',run_id,'--status',status,'--json'])
    result=receipt.get('result') or {};rows=result.get('tasks')
    if result.get('runId')!=run_id or not isinstance(rows,list):
        raise Rejected(f'native {status}-task inventory is incomplete')
    if any(not isinstance(row,dict) or row.get('run_id')!=run_id for row in rows):
        raise Rejected(f'native {status}-task inventory contains another Run')
    return rows,receipt


def dispatched_tasks(cli, run_id):
    return tasks_with_status(cli,run_id,'dispatched')


def dispatch_context_task(cli, task_id, terminal, run_id):
    """Bind a task to an existing session without Orca prompt injection.

    MATS supplies the compact prompt and lifecycle route itself.  This path is
    intentionally independent of Orca's optional agent-recognition metadata.
    """
    return run_json([cli,'orchestration','dispatch','--task',task_id,'--to',terminal,
                     '--run',run_id,'--json'])


def fail_task(cli, task_id, run_id, *, reason):
    identifier(task_id);identifier(run_id)
    result=json.dumps({'outcome':'superseded','reason':reason},ensure_ascii=False,separators=(',',':'))
    return run_json([cli,'orchestration','task-update','--id',task_id,'--status','failed',
                     '--result',result,'--run',run_id,'--json'])


def retained_terminal_handle(cli, receipt):
    """Resolve a terminal solely from the retained Codex session identity."""
    live,proof,reacquired=_resolve_live_terminal(cli,None,expected_session=receipt['session_id'],
                                                 expected_workspace=receipt.get('workspace_key'))
    proof=dict(proof);proof['_mats_terminal_recovery']={
        'mode':'session_index_rebound','session_id':receipt['session_id'],
        'terminal':live['handle'],'runtime_handle_replaced':bool(reacquired)}
    proof['_mats_resolved_terminal']=live
    return live['handle'],proof

def _pick(d,*keys):
    for k in keys:
        if isinstance(d,dict) and d.get(k) not in (None,''):
            return d[k]
    return None


def _consistent_identity(name,*values):
    present=[value for value in values if value not in (None,'')]
    if any(not isinstance(value,str) for value in present):
        raise Rejected(f'native {name} identity is not a string')
    unique=list(dict.fromkeys(present))
    if len(unique)>1:raise Rejected(f'native {name} identity conflicts across launch receipts: {unique}')
    return unique[0] if unique else None

def normalize_launch_receipt(start, shown, *, packet_digest, access, fresh_context, effective=None, model_fallback=None, simulation=False, source=None):
    """Convert one worker-start + one worker-show into the semantic receipt.

    Raw Orca names/casing stay here. Controller/Guard never translate them.
    """
    sr=start.get('result') or {}; wr=shown.get('result') or {}
    start_dispatch=sr.get('dispatch') or {}
    dispatch=wr.get('dispatch') or {}; worker=wr.get('worker') or {}; terminal=wr.get('terminal') or {}
    run_id=_consistent_identity('Run',_pick(sr,'runId','run_id'),_pick(start_dispatch,'run_id','runId'),
                                _pick(dispatch,'run_id','runId'))
    task_id=_consistent_identity('Task',_pick(sr,'taskId','task_id'),_pick(start_dispatch,'task_id','taskId'),
                                 _pick(dispatch,'task_id','taskId'))
    dispatch_id=_consistent_identity('Dispatch',_pick(sr,'dispatchId','dispatch_id'),
            _pick(start_dispatch,'id','dispatch_id','dispatchId'),_pick(dispatch,'id','dispatch_id','dispatchId'))
    session_id=_codex_session_id(terminal) or _pick(worker,'process_incarnation','processIncarnation') or _pick(dispatch,'process_incarnation','processIncarnation')
    workspace_key=_pick(worker,'worktree_id','worktreeId') or _pick(terminal,'worktreeId','worktree_id')
    workspace_path=_pick(terminal,'worktreePath','worktree_path') or _pick(worker,'worktree_path','worktreePath')
    eff=effective or normalize_effective(((sr.get('launch') or {}).get('effective')))
    values={'run_id':run_id,'task_id':task_id,'dispatch_id':dispatch_id,'session_id':session_id,'workspace_key':workspace_key,'workspace_path':workspace_path}
    missing=[k for k,v in values.items() if not isinstance(v,str) or not v]
    if missing: raise Rejected(f'worker-start/show cannot attest semantic launch receipt fields: {missing}')
    receipt={'schema_version':9,**values,'access':access,'fresh_context':bool(fresh_context),'effective':eff,'packet_digest':packet_digest,
             'source':source or 'MATS normalized native Orca worker-start + worker-show','simulation':bool(simulation)}
    if isinstance(model_fallback,dict) and model_fallback.get('used'):
        receipt['model_fallback']={'used':True,'reason':model_fallback.get('reason')}
    return receipt


def terminal_send_argv(cli, terminal, text, *, submit=True):
    argv=[cli,'terminal','send','--terminal',terminal,'--text',text.rstrip('\r\n')]
    if submit: argv.append('--enter')
    return argv+['--json']

def terminal_send(cli, terminal, text): return run_json(terminal_send_argv(cli,terminal,text,submit=True))

def terminal_submit_argv(cli,terminal):
    """Press Enter without relying on an empty --text payload."""
    return [cli,'terminal','send','--terminal',terminal,'--enter','--json']

def terminal_submit(cli,terminal): return run_json(terminal_submit_argv(cli,terminal))

def send_dispatch_adjustment(cli, *, run_id, task_id, dispatch_id, session_id, workspace_key,
                             control_session, instructions):
    """Wake one exact active Owner with a compact in-scope adjustment."""
    identifier(run_id);identifier(task_id);identifier(dispatch_id)
    if not isinstance(session_id,str) or not session_id or not isinstance(workspace_key,str) or not workspace_key:
        raise Rejected('active Owner steering requires its session and workspace identity')
    if not isinstance(control_session,str) or not control_session:
        raise Rejected('active Owner steering requires the supervising Control session')
    if not isinstance(instructions,str) or not instructions.strip():
        raise Rejected('active Owner steering requires one nonempty user adjustment')
    body='\n'.join([
        '=== MATS USER ADJUSTMENT (VERBATIM, SUBORDINATE) ===',
        f'Run/task/dispatch: {run_id} / {task_id} / {dispatch_id}.',
        f'Supervising Control session: {control_session}.',
        'Apply this only within the current role/WP/authority and existing external-mutation limits. If it conflicts with the current contract, report plan_conflict; do not silently redesign the plan.',
        'Continue locally executable work to a candidate or concrete blocker; an unfinished turn is not a checkpoint.',
        'After any required Skill load or approach statement, immediately execute the concrete work in this same turn; never end with only intent, diagnosis or a next-step description.',
        '',instructions.strip(),'','--- END USER ADJUSTMENT ---',
    ])
    shown=worker_show(cli,dispatch_id);native=shown.get('result') or {};dispatch=native.get('dispatch') or {}
    if (_pick(dispatch,'id','dispatch_id','dispatchId')!=dispatch_id or
            _pick(dispatch,'task_id','taskId')!=task_id or _pick(dispatch,'run_id','runId')!=run_id or
            dispatch.get('status')!='dispatched'):
        raise Rejected('active Owner steering cannot attest the current dispatch identity')
    terminal=native.get('terminal') or {}
    live,proof,_reacquired=_resolve_live_terminal(cli,_pick(terminal,'handle'),expected_session=session_id,
                                                  expected_workspace=workspace_key)
    delivery=terminal_send(cli,live['handle'],body)
    submit=terminal_submit(cli,live['handle'])
    return {'ok':True,'result':{'dispatchId':dispatch_id,'terminal':live['handle'],'woken':True},
            'native_worker_show_receipt':shown,'native_terminal_inventory_receipt':proof,
            'native_delivery_receipt':delivery,'native_submit_receipt':submit}

def wait_events(cli, *, timeout_ms=1_200_000):
    if timeout_ms < 1_200_000:
        raise Rejected('managed wait timeout must be at least 1200000 ms (20 minutes)')
    receipt=run_json([cli,'orchestration','check','--wait','--types','worker_done,escalation,question','--timeout-ms',str(timeout_ms),'--json'])
    result=receipt.get('result') or {};timed_out=bool(result.get('timedOut'));messages=result.get('messages') or []
    return {'mode':'event_driven','timeout_ms':timeout_ms,'status':'checkpoint' if timed_out and not messages else 'events','messages':messages,'native_receipt':receipt,
            'note':'timeout/checkpoint is not worker failure; wait again unless an authoritative terminal/lifecycle event requires action' if timed_out and not messages else 'process every returned event before the next wait'}


def claim_available_events(cli, *, timeout_ms=1_200_000, claim_timeout_ms=5_000):
    """Nonblocking Run-mail probe; claim a visible FIFO batch exactly once."""
    if timeout_ms < 1_200_000:
        raise Rejected('managed wait timeout must be at least 1200000 ms (20 minutes)')
    if not isinstance(claim_timeout_ms,int) or claim_timeout_ms < 1:
        raise Rejected('event claim timeout must be a positive integer')
    kinds='worker_done,escalation,question'
    peek=run_json([cli,'orchestration','check','--peek','--types',kinds,'--json'])
    messages=(peek.get('result') or {}).get('messages') or []
    if not messages:return None
    receipt=run_json([cli,'orchestration','check','--wait','--types',kinds,
                      '--timeout-ms',str(min(claim_timeout_ms,timeout_ms)),'--json'])
    result=receipt.get('result') or {};messages=result.get('messages') or []
    if not messages or not result.get('deliveryId'):
        raise Rejected('visible lifecycle mail could not be claimed as an exact delivery batch')
    return {'mode':'event_or_context','timeout_ms':timeout_ms,'status':'events',
            'messages':messages,'native_receipt':receipt,
            'note':'process every returned event before the next wait'}


def wait_events_or_context_completion(cli, dispatch_ids, *, timeout_ms=1_200_000, poll_interval_ms=5_000):
    """Wait for lifecycle mail or a proved context-only Dispatch completion.

    Orca's plain context dispatch can finish a Codex turn without emitting
    ``worker_done``.  Control may therefore start one wait immediately after a
    continuation: this bridge polls silently and returns only when lifecycle
    mail, exact Dispatch completion, or the ordinary checkpoint is observed.
    """
    if timeout_ms < 1_200_000:
        raise Rejected('managed wait timeout must be at least 1200000 ms (20 minutes)')
    if not isinstance(poll_interval_ms,int) or poll_interval_ms < 1:
        raise Rejected('context completion poll interval must be a positive integer')
    if not isinstance(dispatch_ids,(list,tuple)) or not dispatch_ids:
        raise Rejected('context completion wait requires at least one Dispatch identity')
    dispatch_ids=list(dict.fromkeys(dispatch_ids))
    for dispatch_id in dispatch_ids:identifier(dispatch_id)

    kinds='worker_done,escalation,question'
    deadline=time.monotonic()+(timeout_ms/1000)

    def check(*,wait=False,window_ms=None):
        if not wait:
            return claim_available_events(cli,timeout_ms=timeout_ms,claim_timeout_ms=poll_interval_ms)
        argv=[cli,'orchestration','check','--wait' if wait else '--peek','--types',kinds]
        if wait:argv += ['--timeout-ms',str(window_ms)]
        receipt=run_json([*argv,'--json'])
        result=receipt.get('result') or {};messages=result.get('messages') or []
        if messages:
            if not result.get('deliveryId'):
                raise Rejected('native lifecycle wait returned messages without a delivery batch identity')
            return {'mode':'event_or_context','timeout_ms':timeout_ms,'status':'events',
                    'messages':messages,'native_receipt':receipt,
                    'note':'process every returned event before the next wait'}
        return None

    while True:
        event=check()
        if event:return event
        completed=None;native_status=None;shown_receipt=None
        for dispatch_id in dispatch_ids:
            shown=worker_show(cli,dispatch_id);native=shown.get('result') or {};dispatch=native.get('dispatch') or {}
            if _pick(dispatch,'id','dispatch_id','dispatchId')!=dispatch_id:
                raise Rejected('worker-show cannot attest the monitored context Dispatch identity')
            if dispatch.get('status') in {'completed','failed','stopped','abandoned','cancelled'}:
                completed=dispatch_id;native_status=dispatch.get('status');shown_receipt=shown;break
        if completed is not None:
            # Lifecycle mail is authoritative if it raced with the completion
            # probe.  Only a second empty peek permits no-delivery recovery.
            event=check()
            if event:return event
            return {'mode':'event_or_context','timeout_ms':timeout_ms,
                    'status':'dispatch_settled_without_event','messages':[],
                    'dispatch_id':completed,'native_status':native_status,'native_receipt':shown_receipt,
                    'note':'the exact Dispatch settled without lifecycle delivery; Control must recover only a successful current context continuation'}
        remaining_ms=max(0,int((deadline-time.monotonic())*1000))
        if remaining_ms<=0:
            return {'mode':'event_or_context','timeout_ms':timeout_ms,'status':'checkpoint','messages':[],
                    'native_receipt':None,
                    'note':'timeout/checkpoint is not worker failure; wait again unless an authoritative terminal/lifecycle event requires action'}
        event=check(wait=True,window_ms=min(poll_interval_ms,remaining_ms))
        if event:return event


def acknowledge_events(cli,delivery_id):
    """Acknowledge one already processed native FIFO batch without consuming its successor."""
    identifier(delivery_id)
    return run_json([cli,'orchestration','check','--ack',delivery_id,'--peek','--types','worker_done,escalation,question','--json'])
