"""Single managed CLI. Host quirks are normalized below this boundary."""
import argparse,sys
from pathlib import Path
SCRIPTS=Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:sys.path.insert(0,str(SCRIPTS))
if __name__=='__main__' and Path(sys.prefix).resolve() != (SCRIPTS.parent/'.venv').resolve():
    print('MATS_RUNTIME_ERROR: use the installed bin/mats launcher',file=sys.stderr);raise SystemExit(126)
from common import Rejected,atomic_write,digest,emit_utf8,encode,load,logical_relative,rejection_payload,require_managed_runtime
from guards import Guards
import advance as advancement,dispatchctl,role_spawn
from native_orca import acknowledge_events, capture_runtime_view, claim_available_events, ensure_run_context, retained_terminal_handle, send_dispatch_adjustment, send_owner_answer, terminal_send, terminal_submit, wait_events, wait_events_or_context_completion
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
  query            ask a retained Owner one answer-only domain question
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
  answer           return one script-correlated Owner query answer

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


def _retained_owner(g,wp):
    state=g.state();source_ref=state['current_candidates'].get(wp) or state['latest_sources'].get(wp)
    if not source_ref:
        raise Rejected('Owner query requires a retained same-WP source',code='RETAINED_OWNER_NOT_FOUND')
    source=g.files.get(source_ref);binding_ref=source.get('binding_ref')
    if not isinstance(binding_ref,dict):raise Rejected('retained Owner source lacks its binding')
    binding=g.files.get(binding_ref);packet=g.files.get(binding['packet_ref'])
    if binding.get('role') not in OWNERS or packet.get('wp_id')!=wp:
        raise Rejected('retained source is not a same-WP Owner')
    g.resume_anchor(binding['packet_ref'])
    return binding_ref,binding


def _owner_query_records(g,wp=None):
    root=g.files.root/'tmp'/'owner-queries'
    if not root.exists():return []
    out=[]
    for path in sorted(root.glob('*.yaml')):
        value=load(path)
        required={'schema_version','kind','id','status','run_id','wp_id','question','question_digest',
                  'binding_ref','control_session','answer_path'}
        if (not isinstance(value,dict) or set(value)-required-{'answer_digest','received_delivery_id'} or
                not required.issubset(value) or value['schema_version']!=1 or value['kind']!='owner_query' or
                value['status'] not in {'pending','sent'} or path.stem!=value['id'] or
                any(not isinstance(value[key],str) or not value[key] for key in
                    ('id','run_id','wp_id','question','question_digest','control_session','answer_path')) or
                not isinstance(value['binding_ref'],dict) or
                (value.get('answer_digest') is not None and not isinstance(value['answer_digest'],str)) or
                (value.get('received_delivery_id') is not None and not isinstance(value['received_delivery_id'],str)) or
                (value['status']=='pending' and ('answer_digest' in value or 'received_delivery_id' in value)) or
                (value['status']=='sent' and 'answer_digest' not in value) or
                ('received_delivery_id' in value and value['status']!='sent') or
                digest(value['question'])!=value['question_digest']):
            raise Rejected('invalid script-owned pending Owner query')
        if wp is None or value['wp_id']==wp:out.append((path,value))
    return out


def _owner_answer_messages(g,messages,delivery_id):
    pending={value['id']:(path,value) for path,value in _owner_query_records(g)}
    answers=[];matched=set()
    for message in messages:
        if not isinstance(message,dict) or message.get('type')!='status':continue
        subject=message.get('subject')
        prefix='MATS owner answer '
        if not isinstance(subject,str) or not subject.startswith(prefix):continue
        query_id=subject[len(prefix):]
        if query_id in matched:raise Rejected('native batch repeats one Owner answer')
        item=pending.get(query_id)
        if item is None:raise Rejected('Owner answer has no exact pending query')
        _path,record=item;answer=message.get('body')
        if not isinstance(answer,str) or not answer.strip():raise Rejected('Owner answer event has no body')
        if record['status']!='sent' or record.get('answer_digest')!=digest(answer.strip()):
            raise Rejected('Owner answer does not match the script-submitted reply')
        received=record.get('received_delivery_id')
        if received is not None and received!=delivery_id:
            raise Rejected('Owner answer was already received through another native delivery')
        matched.add(query_id)
        if received is None:answers.append({'query_id':query_id,'wp':record['wp_id'],'answer':answer.strip()})
    return answers,matched


def _clear_owner_answers(g,answers):
    for item in answers:
        query=g.files.owner_query_path(item['query_id']);answer=g.files.owner_answer_path(item['query_id'])
        query.unlink(missing_ok=True);answer.unlink(missing_ok=True)


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
    if cmd=='query':
        ap=argparse.ArgumentParser(description='Ask one retained Owner an answer-only domain question. The exact question is sent once; no packet, candidate or full init is created.')
        ap.add_argument('--wp',required=True);source=ap.add_mutually_exclusive_group(required=True)
        source.add_argument('--question',help='exact user question')
        source.add_argument('--question-file',help='UTF-8 file under .task/tmp containing the exact question')
        ap.add_argument('--cli',default='orca',help=argparse.SUPPRESS);a=ap.parse_args(argv)
        try:
            g=Guards(repo);question=a.question
            if a.question_file:
                path=g.files.control_path(a.question_file,prefixes=('tmp',))
                if not path.is_file():raise Rejected('Owner query file not found under .task/tmp')
                question=path.read_text(encoding='utf-8')
            question=(question or '').strip()
            if not question:raise Rejected('Owner query must be nonempty')
            if len(question.encode('utf-8'))>32768:raise Rejected('Owner query exceeds 32 KiB')
            binding_ref,binding=_retained_owner(g,a.wp);receipt=binding['receipt']
            query_id='q'+digest({'wp':a.wp,'question':question,'session_id':receipt['session_id']})[:20]
            pending=_owner_query_records(g,a.wp)
            same=[value for _path,value in pending if value['id']==query_id]
            if same:
                emit_utf8({'status':'pending','reason_code':'OWNER_QUERY_ALREADY_PENDING','query_id':query_id,
                           'wp':a.wp,'next_operation':{'command':'wait','actor':'control'}});return 0
            if pending:
                raise Rejected('another Owner query is already pending for this WP',code='OWNER_QUERY_PENDING')
            ensure_run_context(a.cli,g.state()['run_id']);terminal,_proof=retained_terminal_handle(a.cli,receipt)
            answer_path=g.files.owner_answer_path(query_id,create=True)
            record={'schema_version':1,'kind':'owner_query','id':query_id,'status':'pending','run_id':g.state()['run_id'],
                    'wp_id':a.wp,'question':question,'question_digest':digest(question),'binding_ref':binding_ref,
                    'control_session':_control_session(g),'answer_path':logical_relative(g.files.root,answer_path)}
            query_path=g.files.owner_query_path(query_id,create=True);atomic_write(query_path,encode(record))
            prompt=role_spawn.owner_query_prompt(query_id=query_id,wp=a.wp,question=question,
                    control_session=record['control_session'],answer_path=answer_path,repo=g.files.repo)
            try:terminal_send(a.cli,terminal,prompt)
            except Exception:
                query_path.unlink(missing_ok=True);answer_path.unlink(missing_ok=True);raise
            terminal_submit(a.cli,terminal)
            emit_utf8({'status':'sent','reason_code':'OWNER_QUERY_SENT','query_id':query_id,'wp':a.wp,
                       'next_operation':{'command':'wait','actor':'control'}});return 0
        except (Rejected,OSError,ValueError,KeyError,TypeError,UnicodeError) as e:
            emit_utf8(rejection_payload(e),error=True);return 2
    if cmd=='answer':
        ap=argparse.ArgumentParser(description='Submit the exact script-correlated response for one pending Owner query.')
        ap.add_argument('query_id');ap.add_argument('--cli',default='orca',help=argparse.SUPPRESS);a=ap.parse_args(argv)
        try:
            g=Guards(repo);path=g.files.owner_query_path(a.query_id)
            if not path.is_file():raise Rejected('pending Owner query not found')
            record=load(path);matches=[value for _path,value in _owner_query_records(g) if value['id']==a.query_id]
            if len(matches)!=1:raise Rejected('pending Owner query identity is ambiguous')
            record=matches[0]
            if record['status']=='sent':
                emit_utf8({'status':'sent','reason_code':'OWNER_ANSWER_ALREADY_SENT','query_id':a.query_id});return 0
            answer_path=g.files.control_path(record['answer_path'],prefixes=('tmp/owner-answers',))
            if answer_path!=g.files.owner_answer_path(a.query_id) or not answer_path.is_file():
                raise Rejected('exact Owner answer file is missing')
            if answer_path.stat().st_size>32768:raise Rejected('Owner answer exceeds 32 KiB')
            answer=answer_path.read_text(encoding='utf-8').strip()
            if not answer:raise Rejected('Owner answer is empty')
            binding=g.files.get(record['binding_ref']);receipt=binding['receipt']
            if record['run_id']!=g.state()['run_id']:raise Rejected('Owner query belongs to another Run')
            ensure_run_context(a.cli,record['run_id']);terminal,_proof=retained_terminal_handle(a.cli,receipt)
            send_owner_answer(a.cli,run_id=record['run_id'],task_id=receipt['task_id'],
                    dispatch_id=receipt['dispatch_id'],terminal=terminal,query_id=a.query_id,answer=answer)
            record={**record,'status':'sent','answer_digest':digest(answer)};atomic_write(path,encode(record))
            emit_utf8({'status':'sent','reason_code':'OWNER_ANSWER_SENT','query_id':a.query_id});return 0
        except (Rejected,OSError,ValueError,KeyError,TypeError,UnicodeError) as e:
            emit_utf8(rejection_payload(e),error=True);return 2
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
            view=None;context_dispatches=[];monitored=[];pending_queries=[]
            if not a.actor_packet:
                pending_queries=_owner_query_records(g)
                view=capture_runtime_view(g,a.cli)[0]
                context_dispatches=advancement.context_wait_dispatches(g,view)
                monitored=list(dict.fromkeys([item['dispatch_id'] for item in view.get('active_dispatches',[])]+context_dispatches))
            if a.actor_packet:
                emit_utf8('# MATS_WAIT event-driven blocking wait started; no progress broadcasts until an event or timeout checkpoint.\n',error=True)
                out=wait_events(a.cli,timeout_ms=a.timeout_ms)
            elif monitored:
                emit_utf8('# MATS_WAIT event-driven blocking wait started; no progress broadcasts until an event, Dispatch settlement or timeout checkpoint.\n',error=True)
                if pending_queries:
                    out=wait_events_or_context_completion(a.cli,monitored,timeout_ms=a.timeout_ms,include_status=True)
                else:out=wait_events_or_context_completion(a.cli,monitored,timeout_ms=a.timeout_ms)
            elif pending_queries:
                emit_utf8('# MATS_WAIT answer-only Owner query wait started; no progress broadcasts and no duplicate query until its answer or timeout checkpoint.\n',error=True)
                out=wait_events(a.cli,timeout_ms=a.timeout_ms,include_status=True)
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
            delivery_id=None
            if messages:
                try:delivery_id=out['native_receipt']['result']['deliveryId']
                except (KeyError,TypeError):raise Rejected('native event batch lacks deliveryId')
            owner_answers,answer_ids=_owner_answer_messages(g,messages,delivery_id)
            def is_owner_answer(message):
                return (isinstance(message,dict) and message.get('type')=='status' and
                        isinstance(message.get('subject'),str) and
                        message['subject'].removeprefix('MATS owner answer ') in answer_ids)
            has_worker_done=any(isinstance(m,dict) and m.get('type')=='worker_done' for m in messages)
            if has_worker_done:
                # One native delivery may contain both an answer-only receipt and
                # ordinary worker_done.  Stage only the latter semantics and keep
                # the query until result imports perform the batch's single ack.
                if owner_answers:
                    for path,record in _owner_query_records(g):
                        if record['id'] in answer_ids:
                            atomic_write(path,encode({**record,'received_delivery_id':delivery_id}))
                ready=g.stage_worker_done_batch([m for m in messages if not is_owner_answer(m)],delivery_id)
            elif messages:
                # Pure question/escalation batches carry no import transaction.
                # Once captured for this response they must be acknowledged or
                # Orca will redeliver the same FIFO batch forever.  A batch that
                # contains worker_done is deliberately left unacknowledged until
                # the staged result import succeeds.
                acknowledge_events(a.cli,delivery_id)
                out['semantic_events_acknowledged']=True
                if owner_answers:_clear_owner_answers(g,owner_answers)
            try:anchor=g.resume_anchor(pref);anchor['stale']=False
            except Rejected as exc:
                anchor={**before,'stale':True,'permitted_next_actions':['return_to_control'],
                        'refresh_rule':f'refresh before processing events; semantic context changed while waiting: {exc}'}
            answer_only=bool(messages) and all(isinstance(m,dict) and m.get('type')=='status' and
                isinstance(m.get('subject'),str) and m['subject'].removeprefix('MATS owner answer ') in answer_ids for m in messages)
            mechanical=(out.get('status')=='checkpoint' and not messages) or bool(messages) and all(isinstance(m,dict) and m.get('type')=='worker_done' for m in messages) or answer_only
            if not anchor['stale'] and mechanical:
                anchor['required_rereads']=[]
                anchor['permitted_next_actions']=['import_ready_results'] if ready else ['return_owner_answer'] if owner_answers else ['wait_again']
                anchor['refresh_rule']='No reread is required for this verified mechanical event/checkpoint; reread the role/routing authorities only after compaction, interruption, semantic change or authority uncertainty.'
            out.pop('native_receipt',None);out['native_verified']=True
            if owner_answers:
                out['reason_code']='OWNER_ANSWER_READY';out['owner_answers']=owner_answers;out['response_required']=True
                out['note']='Return each exact answer to the user once; do not dispatch, continue, or ask the Owner again for this query.'
                if answer_only:out.pop('messages',None)
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
