"""CLI for semantic artifacts; internal lifecycle closure is never caller-authored."""
import argparse,copy,os,shutil,sys
from pathlib import Path
SCRIPTS=Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:sys.path.insert(0,str(SCRIPTS))
if __name__=='__main__' and Path(sys.prefix).resolve() != (SCRIPTS.parent/'.venv').resolve():
    print('MATS_RUNTIME_ERROR: use the installed bin/mats launcher',file=sys.stderr);raise SystemExit(126)
from common import ROOT,Rejected,atomic_write,digest,emit_utf8,encode,load,logical_relative,managed_runtime_status,rejection_payload,require_managed_runtime
from forms import is_form_bytes,parse_form
from guards import Guards
from contracts import validate
from native_orca import acknowledge_events, capture_runtime_view, current_run_id, release_worker
from packets import hydrate
from routing import validate_policy,validate_operator
from verification import repository_inventory

ONE_SHOT_ROLES={'review_r1','review_r2','planner','luna_aux','synthesis'}


def _task_load(g,path,*,prefixes=()):
    return g.files.load_control(path,prefixes=prefixes)


def _internal_ref(g,value,folder):
    """Resolve only a current artifact ID or milestone-nested artifact path."""
    p=Path(value)
    if len(p.parts)==1 and p.suffix.lower() not in {'.yaml','.yml'}:
        try:
            ref=g.files.named(folder,value)
        except Rejected:
            ref=None
        if ref is not None:return ref
    path=g.files.control_path(value)
    logical=logical_relative(g.files.root,path)
    if g.files.is_folder_path(logical,folder.rstrip('/')):
        obj=load(path)
        return {'path':logical,'sha256':digest(obj)}
    raise Rejected('expected an artifact ID or milestone-nested artifact path; ref-wrapper files are not accepted')


def _doctor_output():
    validate_policy(load(ROOT/'config/policy.yaml'));validate_operator(load(ROOT/'config/operator-defaults.yaml'))
    runtime=managed_runtime_status()
    return {'version':'1.2.0','schema_version':9,'policy_valid':True,'operator_defaults_valid':True,
            'live_orca_verified':False,'model_calls':0,'orca_executable':shutil.which('orca') or shutil.which('orca-ide'),
            **runtime,'jsonschema_external_required':False,
            'note':'Binary presence is not runtime/model/permission verification. No live launch is made.'}


def _bound_packet_workspace(g,packet_ref):
    bindings=[b for _ref,b in g.files.all('bindings') if b.get('packet_ref')==packet_ref]
    if not bindings:raise Rejected('packet has no managed binding')
    paths={str(Path(b['receipt']['workspace_path']).resolve()) for b in bindings}
    if len(paths)!=1:raise Rejected('packet bindings disagree on their assigned workspace')
    return next(iter(paths))


def _finalize_delivery(g,packet_ref,workspace=None):
    packet=g.files.get(packet_ref);path=g.files.delivery_path(packet['id'])
    if not path.is_file():raise Rejected('injected delivery form is missing')
    raw=path.read_bytes();form_input=is_form_bytes(raw)
    draft=parse_form(raw,expected_kind=packet['output_contract']) if form_input else load(path)
    if workspace is None:workspace=_bound_packet_workspace(g,packet_ref)
    prepared=g.prepare_delivery(packet_ref,draft,workspace=workspace)
    out=g.check_delivery(packet_ref,prepared);out['canonicalized']=form_input or prepared!=draft
    if form_input or prepared!=draft:atomic_write(path,encode(prepared))
    return out


def _bootstrap(g,name,project_id,goal_path,run_id,simulation):
    d=g.files.milestone_dir(name);source=g.files.control_path(goal_path,prefixes=('tmp',))
    try:goal=source.read_text(encoding='utf-8').strip()
    except UnicodeError as exc:raise Rejected('bootstrap goal must be UTF-8') from exc
    if not goal or len(goal.encode('utf-8'))>65536:raise Rejected('bootstrap goal must contain 1..65536 UTF-8 bytes')
    target=d/'goal.txt'
    if source.resolve()!=target.resolve():atomic_write(target,goal.encode('utf-8'))
    project={'schema_version':9,'project_id':project_id,'goal':goal,'phase':'planning','commitments':[],
             'boundaries':[],'strategic_risks':[],'working_hypotheses':[],'open_questions':[]}
    plan={'schema_version':9,'plan_id':name,'project_id':project_id,'version':1,'work_packages':[]}
    request={'reason':'bootstrap','question':'Produce the full project commitments and coarse Work Packages from the stated goal and deterministic repository inventory.',
             'source_refs':[],'directive_ids':[],'affected_wp_ids':[]}
    inventory=repository_inventory(g.files.repo)
    for path,value in ((d/'project.yaml',project),(d/'plan.yaml',plan),(d/'planning-request.yaml',request),(d/'inventory.yaml',inventory)):
        atomic_write(path,encode(value))
    g.initialize(project,plan,run_id,simulation=simulation,bootstrap_inventory=inventory)
    g.attach_current_control(os.environ.get('CODEX_SESSION_ID'))
    return {'initialized':True,'milestone_id':name,
            'next_operation':{'command':'dispatch','operation':'planner','request':str(d/'planning-request.yaml')}}


def _normalize_repo_order(argv):
    argv=list(sys.argv[1:] if argv is None else argv)
    repo='.';out=[];i=0
    while i < len(argv):
        t=argv[i]
        if t=='--repo':
            if i+1>=len(argv): raise Rejected('--repo requires a value')
            repo=argv[i+1];i+=2;continue
        if t.startswith('--repo='):
            repo=t.split('=',1)[1]
            if not repo: raise Rejected('--repo requires a value')
            i+=1;continue
        out.append(t);i+=1
    return ['--repo',repo,*out]


def _lifecycle_operation(g,kind,native_id):
    """Return a previously confirmed native step, if one exists."""
    path=g.files.lifecycle_operation_path(kind,native_id)
    if not path.is_file():return None
    value=load(path)
    expected={'schema_version':1,'kind':kind,'native_id':native_id,'confirmed':True}
    if value!=expected:raise Rejected(f'conflicting {kind} lifecycle operation record')
    return value


def _confirm_lifecycle_operation(g,kind,native_id):
    value={'schema_version':1,'kind':kind,'native_id':native_id,'confirmed':True}
    path=g.files.lifecycle_operation_path(kind,native_id,create=True)
    try:atomic_write(path,encode(value),immutable=True)
    except FileExistsError:
        if load(path)!=value:raise Rejected(f'conflicting {kind} lifecycle operation record')
    return value


def _release_once(g,dispatch_id,cli,*,retry_command):
    if _lifecycle_operation(g,'release',dispatch_id) is not None:return False
    try:receipt=release_worker(cli,dispatch_id)
    except Rejected as exc:
        raise Rejected(str(exc),code='OWNER_RELEASE_UNCONFIRMED',next_operation=retry_command) from exc
    _confirm_lifecycle_operation(g,'release',dispatch_id)
    return receipt


def _finish_completion_batch(g,event,cli):
    """Release every imported one-shot in a batch before its single ack.

    Confirmed release/ack steps are durable and script-only, so a result retry
    resumes the incomplete step instead of repeating earlier native mutations.
    """
    if not g.completion_batch_imported(event):
        return {'acknowledged':False,'released':[],'release_error':None,'ack_error':None}
    released=[]
    for dispatch_id in event['batch_worker_done_dispatches']:
        binding_ref=g.files.named('bindings',dispatch_id)
        if binding_ref is None:raise Rejected('completion batch references an unknown binding')
        binding=g.files.get(binding_ref)
        if binding['role'] not in ONE_SHOT_ROLES:continue
        if _lifecycle_operation(g,'release',dispatch_id) is None:
            try:release_worker(cli,dispatch_id)
            except Rejected as exc:
                return {'acknowledged':False,'released':released,'release_error':str(exc),'ack_error':None}
            _confirm_lifecycle_operation(g,'release',dispatch_id)
        released.append(dispatch_id)
    delivery_id=event['delivery_id']
    if _lifecycle_operation(g,'ack',delivery_id) is None:
        try:acknowledge_events(cli,delivery_id)
        except Rejected as exc:
            return {'acknowledged':False,'released':released,'release_error':None,'ack_error':str(exc)}
        _confirm_lifecycle_operation(g,'ack',delivery_id)
    g.files.clear_owner_queries_for_delivery(delivery_id)
    g.clear_completion_batch(event)
    return {'acknowledged':True,'released':released,'release_error':None,'ack_error':None}


def accept_with_mechanical_owner_release(g,wp_id,view,cli):
    """Accept, releasing the retained Owner only after Guard proves it is sole blocker."""
    try:return g.accept(wp_id,view)
    except Rejected as exc:
        if exc.code!='OWNER_RELEASE_REQUIRED':raise
    state=g.state();candidate_ref=state['current_candidates'].get(wp_id)
    if candidate_ref is None:raise Rejected('candidate disappeared before Owner release',code='CANDIDATE_MISSING')
    candidate=g.files.get(candidate_ref);binding=g.files.get(candidate['binding_ref']);dispatch_id=binding['receipt']['dispatch_id']
    release_receipt=_release_once(g,dispatch_id,cli,retry_command={'command':'accept','wp':wp_id})
    fresh_view=capture_runtime_view(g,cli)[0]
    accepted=g.accept(wp_id,fresh_view)
    release_result=(release_receipt or {}).get('result') or {}
    terminal_released=release_result.get('state')=='released'
    return {**accepted,'owner_dispatch_released':True,'owner_session_released':terminal_released,
            'owner_terminal_retained':not terminal_released}


def apply_plan_with_mechanical_owner_release(g,proposal_ref,view,cli):
    """Apply a valid proposal, retiring only affected proven retained Owners."""
    try:return g.apply_plan(proposal_ref,view)
    except Rejected as exc:
        if exc.code!='OWNER_RELEASE_REQUIRED':raise
    drain=g.planner_drain_set(proposal_ref);state=g.state();released=[]
    writers=[u for u in view['workspace_users'] if u['access']=='write' and (u['wp_id'] in drain or u['wp_id'] is None)]
    for user in writers:
        wp_id=user.get('wp_id')
        source_ref=state['current_candidates'].get(wp_id) or state['latest_sources'].get(wp_id)
        if source_ref is None:raise Rejected('affected writer has no proven retained Owner source',code='PLAN_OWNER_IDENTITY_UNRESOLVED')
        source=g.files.get(source_ref);binding=g.files.get(source['binding_ref']);receipt=binding['receipt']
        if binding['role'] not in {'research','engineering'} or receipt['session_id']!=user['session_id']:
            raise Rejected('affected writer does not match the retained Owner identity',code='PLAN_OWNER_IDENTITY_UNRESOLVED')
        dispatch_id=receipt['dispatch_id']
        if dispatch_id not in released:
            _release_once(g,dispatch_id,cli,retry_command={'command':'apply-plan','proposal_ref':proposal_ref['path']})
            released.append(dispatch_id)
    if not released:raise Rejected('Guard requested writer release but no affected Owner was resolvable',code='PLAN_OWNER_IDENTITY_UNRESOLVED')
    fresh_view=capture_runtime_view(g,cli)[0]
    applied=g.apply_plan(proposal_ref,fresh_view)
    return {**applied,'owner_sessions_released':released}


def process_staged_result(g,binding_ref,cli='orca'):
    """Import one staged completion and finish its whole native batch when ready."""
    binding=g.files.get(binding_ref);result_ref,event=g.import_staged_result(binding_ref)
    batch=_finish_completion_batch(g,event,cli)
    acknowledged=batch['acknowledged'];release_error=batch['release_error'];ack_error=batch['ack_error']
    out={'result_ref':result_ref,'worker_done_acknowledged':acknowledged}
    record=g.files.get(result_ref);side_refs=([record['side_request_ref']] if record.get('side_request_ref') else g.side_requests_for_binding(binding_ref))
    if side_refs:out['source_side_request_refs']=side_refs
    if batch['released']:out['batch_one_shot_sessions_released']=batch['released']
    if binding['role'] in ONE_SHOT_ROLES and binding['receipt']['dispatch_id'] in batch['released']:
        out['one_shot_session_released']=True
    if release_error:out['release_retry']='rerun the same idempotent result command; '+release_error
    if ack_error:out['acknowledgement_retry']='rerun the same idempotent result command; '+ack_error
    return out

def main(argv=None):
    argv=_normalize_repo_order(argv)
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--repo',default='.',help='repository containing the .task control root; accepted before or after the command')
    sp=ap.add_subparsers(dest='cmd',required=True,metavar='COMMAND')
    sp.add_parser('activate',help='verify MATS and refresh the current Control session for this repository')
    x=sp.add_parser('bootstrap',description='Initialize from one UTF-8 goal file under .task/tmp. Milestone paths, Run identity, seed contracts, inventory and Control attachment are mechanical.',help='initialize a project from one semantic goal file')
    x.add_argument('name',help='initial milestone ID, for example m0_baseline-recovery');x.add_argument('--project-id',required=True);x.add_argument('--goal-file',required=True,help='UTF-8 goal file anywhere under .task/tmp');x.add_argument('--simulation',action='store_true');x.add_argument('--run-id',help=argparse.SUPPRESS);x.add_argument('--cli',default='orca',help=argparse.SUPPRESS)
    x=sp.add_parser('planner-repair',help='generate an exact repair request from an immutable Planner rejection');x.add_argument('rejection',help='rejection YAML under .task/planner_rejections');x.add_argument('--sha256',required=True,help='expected rejection digest')
    sp.add_parser('planning-request-form',help='generate the fixed Control semantic TSV form for a runtime Planner occasion')
    x=sp.add_parser('planning-request',help='finalize a generated Planner-request form and mechanically archive directives/refs');x.add_argument('form',help='exact generated .task/tmp/planning-request.tsv')
    x=sp.add_parser('operator',help='show or replace offline operator controls');x.add_argument('file',nargs='?',help='replacement YAML under .task; omit to show')
    x=sp.add_parser('validate',help='validate one external YAML file against a named syntax contract');x.add_argument('kind',help='contract kind, such as result, review, side_result or planner_result');x.add_argument('file',help='draft YAML; may be outside .task')
    x=sp.add_parser('deliver',description='Finalize the fixed delivery for one bound packet. Packet digest, delivery path and assigned workspace are derived from MATS state.',help='finalize one child delivery without transaction arguments')
    x.add_argument('packet_ref',help='packet ID or packet artifact path')
    x=sp.add_parser('evidence',description='Bundle evidence for one bound Owner packet. Digest and workspace are derived from its binding.',help='bundle Owner evidence without transaction arguments')
    x.add_argument('packet_ref',help='packet ID or packet artifact path');x.add_argument('output');x.add_argument('inputs',nargs='+')
    sp.add_parser('doctor',help='verify the isolated runtime and private configuration without a model call')
    sp.add_parser('status',help='show current semantic plan/candidate status')
    x=sp.add_parser('directive',help='record one immutable user directive');x.add_argument('file',help='directive YAML under .task')
    x=sp.add_parser('issue',help='issue a semantic packet without launching it');x.add_argument('id');x.add_argument('operation');x.add_argument('--wp');x.add_argument('--request')
    x=sp.add_parser('packet',help='read a packet and optionally resolve payload refs');x.add_argument('ref',help='packet ID or milestone-nested artifact path');x.add_argument('--hydrate',action='store_true');x.add_argument('--hydrate-all',action='store_true')
    x=sp.add_parser('bind',help='bind a normalized native receipt to an issued packet');x.add_argument('packet_ref',help='packet ID or milestone-nested artifact path');x.add_argument('receipt')
    x=sp.add_parser('result',description='Exact single-step recovery for one staged worker_done. Normal wait completion uses `mats advance`; this command resolves the fixed binding draft/completion and closes the batch when ready.',help='recover one verified child-delivery import by binding ID');x.add_argument('binding_ref',help='binding dispatch ID or milestone-nested artifact path');x.add_argument('--cli',default='orca',help=argparse.SUPPRESS)
    x=sp.add_parser('side-request-form',help='generate an Owner/R1 semantic TSV form for a Luna/Synthesis request');x.add_argument('binding_ref',nargs='?',help='source binding ID/path; omitted in a managed child session');x.add_argument('--operation',required=True,choices=['luna_aux','synthesis']);x.add_argument('--caller-session',help=argparse.SUPPRESS)
    x=sp.add_parser('side-request',help='finalize/import a generated Owner/R1 side-request form');x.add_argument('binding_ref',help='binding dispatch ID or milestone-nested artifact path');x.add_argument('request');x.add_argument('--caller-session',help=argparse.SUPPRESS)
    x=sp.add_parser('r0',help='run deterministic checks for the exact current candidate');x.add_argument('candidate_ref',help='result artifact ID or milestone-nested path')
    x=sp.add_parser('accept',help='Control-only guarded acceptance of an exact reviewed WP');x.add_argument('wp');x.add_argument('runtime_view',nargs='?',help=argparse.SUPPRESS);x.add_argument('--cli',default='orca',help=argparse.SUPPRESS)
    x=sp.add_parser('apply-plan',help='Control-only guarded application of an imported Planner proposal');x.add_argument('proposal_ref',help='Planner result artifact ID or milestone-nested path');x.add_argument('runtime_view',nargs='?',help=argparse.SUPPRESS);x.add_argument('--cli',default='orca',help=argparse.SUPPRESS)
    x=sp.add_parser('preflight',help='read-only dispatch admission check against a fresh runtime view');x.add_argument('packet_ref',help='packet ID or milestone-nested artifact path');x.add_argument('runtime_view');x.add_argument('--workspace',required=True);x.add_argument('--access',required=True,choices=['write','read_live','read_snapshot']);x.add_argument('--reuse-session')
    a=ap.parse_args(argv)
    try:
        if a.cmd=='doctor':out=_doctor_output()
        elif a.cmd=='validate':validate(a.kind,load(a.file));out={'valid':True}
        else:
            state_path=Path(a.repo).resolve()/'.task'/'semantic.yaml'
            if a.cmd=='activate':
                _doctor_output()
                if state_path.is_file():
                    g=Guards(a.repo);g.attach_current_control(os.environ.get('CODEX_SESSION_ID'));s=g.state()
                    out={'activated':True,'checks':'passed','initialized':True,'control_attached':True,
                         'plan_version':s['plan']['version'],'run_id':s['run_id']}
                else:
                    out={'activated':True,'checks':'passed','initialized':False,'next_operation':{'command':'bootstrap'}}
            else:g=Guards(a.repo)
            if a.cmd=='activate':pass
            elif a.cmd=='bootstrap':
                run_id=a.run_id or current_run_id(a.cli)
                out=_bootstrap(g,a.name,a.project_id,a.goal_file,run_id,a.simulation)
            elif a.cmd=='planner-repair':
                rp=g.files.control_path(a.rejection,prefixes=('planner_rejections',));rejection=load(rp);validate('planner_rejection',rejection)
                actual=digest(rejection)
                if actual!=a.sha256: raise Rejected('planner rejection hash mismatch')
                rref={'path':logical_relative(g.files.root,rp),'sha256':actual}
                request=copy.deepcopy(rejection['request']);request['repair_of']=rref;validate('planning_request',request)
                qref=g.files.put('requests','planner-repair-'+actual,request)
                occasion={k:request[k] for k in ('reason','question','source_refs','directive_ids','affected_wp_ids')}
                if 'target_milestone_id' in request:occasion['target_milestone_id']=request['target_milestone_id']
                out={'repair_request_ref':qref,'repair_request_path':str(g.files.root/qref['path']),'repair_of':rref,'planning_occasion':occasion}
            elif a.cmd=='planning-request-form':
                path=g.create_planning_request_form()
                out={'form_path':str(path),'next_operation':{'command':'planning-request','form':str(path)}}
            elif a.cmd=='planning-request':
                path=g.files.control_path(a.form,prefixes=('tmp',));expected=g.files.planning_request_form_path()
                if path.resolve()!=expected.resolve():raise Rejected('planning request must use the exact generated form path')
                raw=path.read_bytes()
                if not is_form_bytes(raw):raise Rejected('planning request must remain the generated semantic TSV form')
                value=parse_form(raw,expected_kind='planning_request');out=g.planning_request(value);path.unlink(missing_ok=True)
            elif a.cmd=='deliver':
                pref=_internal_ref(g,a.packet_ref,'packets');out=_finalize_delivery(g,pref)
            elif a.cmd=='evidence':
                pref=_internal_ref(g,a.packet_ref,'packets');workspace=_bound_packet_workspace(g,pref)
                out=g.create_evidence_manifest(pref,a.output,a.inputs,workspace=workspace)
            elif a.cmd=='operator':out=g.set_operator(_task_load(g,a.file)) if a.file else g.operator()
            elif a.cmd=='directive':out=g.directive(_task_load(g,a.file))
            elif a.cmd=='issue':out=g.issue(a.id,a.operation,wp_id=a.wp,request=_task_load(g,a.request) if a.request else None)
            elif a.cmd=='packet':
                ref=_internal_ref(g,a.ref,'packets');out=hydrate(g.files,ref,include_available=a.hydrate_all) if (a.hydrate or a.hydrate_all) else g.files.get(ref)
            elif a.cmd=='bind':out=g.bind(_internal_ref(g,a.packet_ref,'packets'),_task_load(g,a.receipt))
            elif a.cmd=='result':
                binding_ref=_internal_ref(g,a.binding_ref,'bindings')
                out=process_staged_result(g,binding_ref,a.cli)
            elif a.cmd=='side-request-form':
                if a.binding_ref:
                    binding_ref=_internal_ref(g,a.binding_ref,'bindings')
                else:
                    session=os.environ.get('CODEX_SESSION_ID');matches=[ref for ref,b in g.files.all('bindings') if session and b['receipt']['session_id']==session]
                    if len(matches)!=1:raise Rejected('managed child session does not resolve to exactly one binding; use its injected binding ID')
                    binding_ref=matches[0]
                binding=g.files.get(binding_ref);caller=a.caller_session or binding['receipt']['session_id']
                path=g.create_side_request_form(binding_ref,a.operation,caller_session=caller)
                out={'form_path':str(path),'next_operation':{'command':'side-request','binding_ref':binding['receipt']['dispatch_id'],'request':str(path)}}
            elif a.cmd=='side-request':
                binding_ref=_internal_ref(g,a.binding_ref,'bindings');request_path=g.files.control_path(a.request)
                raw=request_path.read_bytes();form_input=is_form_bytes(raw)
                request=parse_form(raw,expected_kind='side_request') if form_input else load(request_path)
                if form_input:
                    expected=g.files.side_request_form_path(g.files.get(binding_ref)['receipt']['dispatch_id'],request['kind'])
                    if request_path.resolve()!=expected.resolve():raise Rejected('side request must use the exact generated form path')
                caller=a.caller_session or g.files.get(binding_ref)['receipt']['session_id']
                out=g.side_request(binding_ref,request,caller_session=caller)
                if form_input:request_path.unlink(missing_ok=True)
            elif a.cmd=='r0':out=g.r0(_internal_ref(g,a.candidate_ref,'results'))
            elif a.cmd=='accept':
                view=_task_load(g,a.runtime_view) if a.runtime_view else capture_runtime_view(g,a.cli)[0]
                out=accept_with_mechanical_owner_release(g,a.wp,view,a.cli)
            elif a.cmd=='apply-plan':
                proposal_ref=_internal_ref(g,a.proposal_ref,'results');view=_task_load(g,a.runtime_view) if a.runtime_view else capture_runtime_view(g,a.cli)[0]
                out=apply_plan_with_mechanical_owner_release(g,proposal_ref,view,a.cli)
            elif a.cmd=='preflight':out=g.preflight(_internal_ref(g,a.packet_ref,'packets'),_task_load(g,a.runtime_view),a.workspace,a.access,reuse_session=a.reuse_session)
            else:
                s=g.state();out={'plan_version':s['plan']['version'],'run_id':s['run_id'],'accepted':s['accepted'],'current_candidates':s['current_candidates'],
                                'native_lifecycle':'query Orca, not this file','simulation':s['simulation']}
        emit_utf8(out);return 0
    except (Rejected,ValueError,KeyError,TypeError,OSError) as e:
        emit_utf8(rejection_payload(e),error=True);return 2

if __name__=='__main__':
    try: require_managed_runtime()
    except RuntimeError as exc:
        emit_utf8(str(exc),error=True);raise SystemExit(126)
    raise SystemExit(main())
