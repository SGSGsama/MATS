"""Single managed CLI. Host quirks are normalized below this boundary."""
import argparse,sys
from pathlib import Path
SCRIPTS=Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:sys.path.insert(0,str(SCRIPTS))
if __name__=='__main__' and Path(sys.prefix).resolve() != (SCRIPTS.parent/'.venv').resolve():
    print('MATS_RUNTIME_ERROR: use the installed bin/mats launcher',file=sys.stderr);raise SystemExit(126)
from common import Rejected,digest,emit_utf8,encode,load,logical_relative,rejection_payload,require_managed_runtime
from guards import Guards
import advance as advancement,dispatchctl,role_spawn
from native_orca import acknowledge_events, capture_runtime_view, claim_available_events, ensure_run_context, send_dispatch_adjustment, terminal_send, wait_events, wait_events_or_context_completion
from routing import OWNERS
from task_validate import validate_task_layout

ROOT_HELP='''usage: mats COMMAND --repo PATH ...

Managed task decomposition and role dispatch. Model and effort are automatic.

Control path:
  activate         verify installation and refresh the current Control session
  bootstrap        initialize from one semantic goal file under .task/tmp
  advance          progress until wait/decision/block/done
  wait             wait for managed events/current context completion
  steer            relay one verbatim in-scope user adjustment to an active Owner
  dispatch         launch only an explicitly returned operation or same-WP continuation
  status           show compact semantic status

Last-resort operator entry:
  migrate          user-directed read-only .task validation; never a normal recovery step

Conditional generated forms:
  planning-request-form   Control's semantic Planner request
  side-request-form       Owner/R1 Aux or Synthesis request

Worker commands are injected exactly; do not discover alternatives:
  deliver          finalize the fixed delivery for a bound packet
  evidence         bundle many Owner evidence files

Recovery commands are used only when returned as an exact next_operation.
Use `mats COMMAND -h` only for a listed command whose exact syntax is missing.
'''

PRIVATE_COMMANDS={'issue','bind','preflight','directive'}
REMOVED_COMMANDS={
    'init':'use bootstrap for a new project',
    'control':'use activate',
    'milestone-paths':'use bootstrap',
    'bootstrap-paths':'use bootstrap',
    'bootstrap-init':'use bootstrap',
    'check-delivery':'use the injected deliver command for current packets',
    'evidence-manifest':'use the injected evidence command for current packets',
}


def _extract_repo(argv):
    """Accept --repo anywhere so callers do not need argparse ordering knowledge."""
    repo='.';out=[];i=0
    while i < len(argv):
        tok=argv[i]
        if tok=='--repo':
            if i+1>=len(argv): raise Rejected('--repo requires a value')
            repo=argv[i+1];i+=2;continue
        if tok.startswith('--repo='):
            repo=tok.split('=',1)[1]
            if not repo: raise Rejected('--repo requires a value')
            i+=1;continue
        out.append(tok);i+=1
    return repo,out


def _control_session(g):
    ref=g.state().get('control_ref')
    if not isinstance(ref,dict):raise Rejected('active Owner steering requires an attached Control session')
    session=g.files.get(ref).get('session_id')
    if not isinstance(session,str) or not session:raise Rejected('attached Control receipt lacks its session identity')
    return session


def _active_owner(g,view,wp):
    active={item['dispatch_id'] for item in view['active_dispatches']}
    matches=[]
    for ref,binding in g.files.all('bindings'):
        receipt=binding['receipt'];packet=g.files.get(binding['packet_ref'])
        if (receipt['dispatch_id'] in active and binding['role'] in OWNERS and packet.get('wp_id')==wp and
                g.imported_dispatch_ref(receipt['dispatch_id']) is None):
            matches.append((ref,binding))
    if not matches:
        raise Rejected('no active same-WP Owner accepts steering; use advance or dispatch --continue-owner as returned',
                       code='ACTIVE_OWNER_NOT_FOUND')
    if len(matches)!=1:
        raise Rejected('multiple active same-WP Owners make the steering target ambiguous',
                       code='ACTIVE_OWNER_AMBIGUOUS')
    return matches[0]


def main(argv=None):
    raw=list(sys.argv[1:] if argv is None else argv)
    try: repo,argv=_extract_repo(raw)
    except Rejected as e:
        emit_utf8(rejection_payload(e),error=True);return 2
    if argv and argv[0]=='dispatchctl-help':
        emit_utf8({'error':'Rejected','reason_code':'DEPRECATED_COMMAND','detail':'the flat recovery/control command catalog is no longer model-facing; use root help or an exact next_operation'},error=True);return 2
    if argv and argv[0] in {'-h','--help'}:
        emit_utf8(ROOT_HELP);return 0
    if not argv:
        emit_utf8(ROOT_HELP,error=True);return 2
    cmd=argv.pop(0)
    if cmd=='migrate':
        ap=argparse.ArgumentParser(description='User-directed, read-only last-resort .task layout validator. Do not run it for ordinary activation, recovery or TASK_MIGRATION_REQUIRED unless the user explicitly requests migration. It never moves, rewrites, deletes or fences anything; load the returned migration guide only when invalid.')
        ap.parse_args(argv)
        try:emit_utf8(validate_task_layout(repo));return 0
        except (Rejected,OSError,ValueError) as e:
            emit_utf8(rejection_payload(e),error=True);return 2
    if cmd in REMOVED_COMMANDS:
        emit_utf8({'error':'Rejected','reason_code':'REMOVED_COMMAND',
                   'detail':f'{cmd} has no compatibility execution path; {REMOVED_COMMANDS[cmd]}'},error=True);return 2
    if cmd in PRIVATE_COMMANDS:
        emit_utf8({'error':'Rejected','reason_code':'PRIVATE_COMMAND','detail':f'{cmd} is an internal transaction primitive; use dispatch/advance or the returned next_operation'},error=True);return 2
    if cmd=='advance': return advancement.main(['--repo',repo,*argv])
    if cmd=='dispatch': return role_spawn.main(['--repo',repo,*argv])
    if cmd=='spawn':
        emit_utf8({'error':'Rejected','reason_code':'DEPRECATED_COMMAND',
                   'detail':'use `mats dispatch`; model/effort are resolved automatically'},error=True);return 2
    if cmd=='wait':
        ap=argparse.ArgumentParser(description='Wait for native events; Control also recovers exact current context-turn completion. A timeout is a checkpoint, not failure.')
        ap.add_argument('--timeout-ms',type=int,default=1_200_000,help='single event wait in milliseconds (default: 1200000)');ap.add_argument('--cli',default='orca',help=argparse.SUPPRESS)
        actor=ap.add_mutually_exclusive_group(required=True);actor.add_argument('--control',action='store_true',help='resume as root Control');actor.add_argument('--actor-packet',help='Owner packet path under .task/packets')
        a=ap.parse_args(argv)
        try:
            g=Guards(repo);pref=None
            if a.actor_packet:
                packet_path=g.files.control_path(a.actor_packet,prefixes=('packets',));packet_value=load(packet_path)
                pref={'path':logical_relative(g.files.root,packet_path),'sha256':digest(packet_value)}
            before=g.resume_anchor(pref)
            view=None;context_dispatches=[];monitored=[]
            if not a.actor_packet:
                view=capture_runtime_view(g,a.cli)[0]
                context_dispatches=advancement.context_wait_dispatches(g,view)
                monitored=list(dict.fromkeys([item['dispatch_id'] for item in view.get('active_dispatches',[])]+context_dispatches))
            if a.actor_packet:
                emit_utf8('# MATS_WAIT event-driven blocking wait started; no progress broadcasts until an event or timeout checkpoint.\n',error=True)
                out=wait_events(a.cli,timeout_ms=a.timeout_ms)
            elif monitored:
                emit_utf8('# MATS_WAIT event-driven blocking wait started; no progress broadcasts until an event, Dispatch settlement or timeout checkpoint.\n',error=True)
                out=wait_events_or_context_completion(a.cli,monitored,timeout_ms=a.timeout_ms)
            else:
                out=claim_available_events(a.cli,timeout_ms=a.timeout_ms)
                if out is None:
                    progressed=advancement.advance(g,cli=a.cli)
                    if progressed.get('status')=='WAIT' and progressed.get('reason_code')=='COMPLETION_EVENT_PENDING':
                        settled={item['dispatch_id'] for item in (view or {}).get('settled_dispatches',[])}
                        missing=progressed.get('dispatch_ids') or [binding['receipt']['dispatch_id']
                                 for _ref,binding in g.files.all('bindings')
                                 if binding['receipt']['dispatch_id'] in settled and
                                 g.imported_dispatch_ref(binding['receipt']['dispatch_id']) is None]
                        progressed={'status':'BLOCKED','reason_code':'LIFECYCLE_DELIVERY_MISSING',
                                    'detail':'a relevant native Dispatch settled without an importable lifecycle delivery; do not wait again',
                                    'dispatch_ids':missing,'trace':progressed.get('trace',[])}
                    progressed['wait_short_circuit']={'reason_code':'NO_ACTIVE_DISPATCH'}
                    emit_utf8(progressed);return 0
            if out.get('status')=='dispatch_settled_without_event':
                dispatch_id=out['dispatch_id']
                if g.imported_dispatch_ref(dispatch_id) is not None:
                    progressed=advancement.advance(g,cli=a.cli)
                    progressed['wait_short_circuit']={'reason_code':'DELIVERY_IMPORTED_DURING_WAIT',
                                                      'dispatch_id':dispatch_id}
                    emit_utf8(progressed);return 0
                if out.get('native_status')=='completed' and dispatch_id in context_dispatches:
                    progressed=advancement.advance(g,cli=a.cli,incomplete_dispatch=dispatch_id)
                    progressed['automatic_recovery']={'reason_code':'CONTEXT_TURN_COMPLETED_WITHOUT_EVENT',
                                                      'dispatch_id':dispatch_id}
                    emit_utf8(progressed);return 0
                emit_utf8({'status':'BLOCKED','reason_code':'LIFECYCLE_DELIVERY_MISSING',
                           'detail':'native Dispatch settled without worker_done/delivery; do not wait again',
                           'dispatch_id':dispatch_id,'native_status':out.get('native_status')});return 0
            messages=out.get('messages') or [];ready=[]
            has_worker_done=any(isinstance(m,dict) and m.get('type')=='worker_done' for m in messages)
            delivery_id=None
            if messages:
                try:delivery_id=out['native_receipt']['result']['deliveryId']
                except (KeyError,TypeError):raise Rejected('native event batch lacks deliveryId')
            if has_worker_done:
                ready=g.stage_worker_done_batch(messages,delivery_id)
            elif messages:
                # Pure question/escalation batches carry no import transaction.
                # Once captured for this response they must be acknowledged or
                # Orca will redeliver the same FIFO batch forever.  A batch that
                # contains worker_done is deliberately left unacknowledged until
                # the staged result import succeeds.
                acknowledge_events(a.cli,delivery_id)
                out['semantic_events_acknowledged']=True
            try:anchor=g.resume_anchor(pref);anchor['stale']=False
            except Rejected as exc:
                anchor={**before,'stale':True,'permitted_next_actions':['return_to_control'],
                        'refresh_rule':f'refresh before processing events; semantic context changed while waiting: {exc}'}
            mechanical=(out.get('status')=='checkpoint' and not messages) or bool(messages) and all(isinstance(m,dict) and m.get('type')=='worker_done' for m in messages)
            if not anchor['stale'] and mechanical:
                anchor['required_rereads']=[]
                anchor['permitted_next_actions']=['import_ready_results'] if ready else ['wait_again']
                anchor['refresh_rule']='No reread is required for this verified mechanical event/checkpoint; reread the role/routing authorities only after compaction, interruption, semantic change or authority uncertainty.'
            out.pop('native_receipt',None);out['native_verified']=True
            if ready:
                out['ready_results']=ready
                out['next_operation']={'command':'advance'}
                out['note']='run `mats advance` for the normal deterministic chain; ready_results remain exact single-step recovery operations'
            out['resume_anchor']=anchor;emit_utf8(out);return 0
        except (Rejected,OSError,ValueError) as e:
            emit_utf8(rejection_payload(e),error=True);return 2
    if cmd=='steer':
        ap=argparse.ArgumentParser(description='Relay one verbatim, in-scope user adjustment to the currently active same-WP Owner. Creates no packet or session.')
        ap.add_argument('--wp',required=True);source=ap.add_mutually_exclusive_group(required=True)
        source.add_argument('--instructions',help='exact user adjustment text')
        source.add_argument('--instructions-file',help='UTF-8 file under .task/tmp containing the exact user adjustment')
        ap.add_argument('--cli',default='orca',help=argparse.SUPPRESS);a=ap.parse_args(argv)
        try:
            g=Guards(repo);instructions=a.instructions
            if a.instructions_file:
                path=g.files.control_path(a.instructions_file,prefixes=('tmp',))
                if not path.is_file():raise Rejected('steering instructions file not found under .task/tmp')
                instructions=path.read_text(encoding='utf-8')
            view,_path=capture_runtime_view(g,a.cli);_ref,binding=_active_owner(g,view,a.wp)
            receipt=binding['receipt'];ensure_run_context(a.cli,g.state()['run_id'])
            send_dispatch_adjustment(a.cli,run_id=receipt['run_id'],task_id=receipt['task_id'],
                    dispatch_id=receipt['dispatch_id'],session_id=receipt['session_id'],
                    workspace_key=receipt['workspace_key'],control_session=_control_session(g),instructions=instructions)
            emit_utf8({'status':'sent','reason_code':'ACTIVE_OWNER_STEERED','wp':a.wp,
                       'task_id':receipt['task_id'],'dispatch_id':receipt['dispatch_id'],
                       'next_operation':{'command':'wait','actor':'control'}});return 0
        except (Rejected,OSError,ValueError,KeyError,TypeError) as e:
            emit_utf8(rejection_payload(e),error=True);return 2
    if cmd=='native-send':
        ap=argparse.ArgumentParser(description='Send one native terminal message. Use only when the loaded workflow authorizes a reply.')
        ap.add_argument('--terminal',required=True,help='native terminal/session target');ap.add_argument('--text',help='inline UTF-8 message');ap.add_argument('--text-file',help='UTF-8 message file');ap.add_argument('--cli',default='orca',help=argparse.SUPPRESS);a=ap.parse_args(argv)
        try:
            if bool(a.text) == bool(a.text_file): raise Rejected('use exactly one of --text or --text-file')
            text=a.text if a.text is not None else open(a.text_file,encoding='utf-8').read()
            out=terminal_send(a.cli,a.terminal,text);emit_utf8(out);return 0
        except (Rejected,OSError,ValueError) as e:
            emit_utf8(rejection_payload(e),error=True);return 2
    return dispatchctl.main(['--repo',repo,cmd,*argv])

if __name__=='__main__':
    try: require_managed_runtime()
    except RuntimeError as exc:
        emit_utf8(str(exc),error=True);raise SystemExit(126)
    raise SystemExit(main())
