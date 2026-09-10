"""Bounded deterministic workflow advancement for root Control."""
import argparse
from pathlib import Path

from common import Rejected, emit_utf8, load, rejection_payload
from dispatchctl import accept_with_mechanical_owner_release, apply_plan_with_mechanical_owner_release, process_staged_result
from guards import Guards
from native_orca import capture_runtime_view
from role_spawn import public_dispatch_result, spawn
from routing import OWNERS


def _public(action):return {k:v for k,v in action.items() if not k.startswith('_')}


def _wait(reason='WORKER_RUNNING'):
    return {'status':'WAIT','reason_code':reason,
            'next_operation':{'command':'wait','actor':'control'}}


def _source_instruction(reason,ref):
    return (f'{reason}. Use the exact source-authored MATS artifact `{ref["path"]}` '
            f'(digest {ref["sha256"]}); preserve its findings/unknowns verbatim and do not broaden the task.')


def _resume_instruction(ref):
    return (f'Resume this same WP now from the exact source-authored MATS artifact `{ref["path"]}` '
            f'(digest {ref["sha256"]}). Continue every locally executable remaining item under the loaded '
            'packet commitments through implementation and verification until a candidate or concrete '
            'external/authority/tool blocker; do not merely restate the prior result or return an unfinished '
            'checkpoint. After any required Skill load or approach statement, immediately execute the concrete '
            'inspect/edit/test work in this same turn; never end with only intent, diagnosis or next-step prose. '
            'Preserve its findings/unknowns verbatim and do not broaden the task.')


def _candidate_context(g,candidate_ref):
    candidate=g.files.get(candidate_ref);binding=g.files.get(candidate['binding_ref']);packet=g.files.get(binding['packet_ref'])
    return candidate,binding,packet


def _side_results(g,request_ref):
    return [(ref,value) for ref,value in g.files.all('results')
            if value.get('kind')=='side_result' and value.get('request_ref')==request_ref]


def _pending_planner(g,state):
    applied=(state.get('last_planner') or {}).get('proposal_ref')
    return [(ref,value) for ref,value in g.files.all('results')
            if value.get('kind')=='planner_result' and ref!=applied
            and value.get('result',{}).get('base_plan_version')==state['plan']['version']]


def _packet_still_relevant(g,state,packet_ref,attempts):
    packet=g.files.get(packet_ref)
    try:g._current_contract(state,packet)
    except Rejected:return False
    role=packet['role'];wp_id=packet.get('wp_id')
    if role in {'research','engineering'}:
        latest_ref=state['latest_sources'].get(wp_id)
        if latest_ref:
            latest_packet=g.files.get(g.files.get(latest_ref)['binding_ref'])['packet_ref']
            if latest_packet!=packet_ref:
                # Packet IDs are one global, zero-padded monotonic sequence. A
                # packet at or before the latest imported Owner source is an
                # obsolete attempt; a later continuation is the pending work
                # that may replace that source and must not be hidden by it.
                latest_packet_value=g.files.get(latest_packet)
                if packet['id']<=latest_packet_value['id']:return False
    elif role.startswith('review_'):
        if state['current_candidates'].get(wp_id)!=packet.get('candidate_ref'):return False
        if g.review_record(packet['candidate_ref'],role):return False
    elif role=='planner' and packet['plan_version']!=state['plan']['version']:return False
    elif role in {'luna_aux','synthesis'} and _side_results(g,packet['request']):return False
    return True


def _pending_binding_action(g,view):
    state=g.state()
    active={item['dispatch_id'] for item in view['active_dispatches']}
    settled={item['dispatch_id']:item['outcome'] for item in view.get('settled_dispatches',[])}
    groups={}
    for ref,binding in g.files.all('bindings'):
        groups.setdefault((binding['packet_ref']['path'],binding['packet_ref']['sha256']),[]).append((ref,binding))
    for attempts in groups.values():
        if any(g.imported_dispatch_ref(binding['receipt']['dispatch_id']) is not None for _ref,binding in attempts):continue
        packet_ref=attempts[-1][1]['packet_ref']
        if not _packet_still_relevant(g,state,packet_ref,attempts):continue
        if any(binding['receipt']['dispatch_id'] in active for _ref,binding in attempts):return _wait()
        dispatches=[binding['receipt']['dispatch_id'] for _ref,binding in attempts]
        if dispatches and all(settled.get(dispatch_id)=='failed' for dispatch_id in dispatches):
            return {'status':'READY','reason_code':'PACKET_RETRY_READY','_kind':'retry','packet_ref':packet_ref,
                    'next_operation':{'command':'dispatch','retry_packet':packet_ref['path'],'retry_sha256':packet_ref['sha256']}}
        pending=_wait('COMPLETION_EVENT_PENDING');pending['dispatch_ids']=dispatches
        return pending
    return None


def context_wait_dispatches(g,view):
    """Return only the newest live/settled no-event Owner context per WP."""
    state=g.state();active={item['dispatch_id'] for item in view.get('active_dispatches',[])}
    succeeded={item['dispatch_id'] for item in view.get('settled_dispatches',[]) if item.get('outcome')=='succeeded'}
    latest={}
    for ref,binding in g.files.all('bindings'):
        receipt=binding.get('receipt') or {}
        if binding.get('role') not in OWNERS:continue
        packet=g.files.get(binding['packet_ref']);wp_id=packet.get('wp_id')
        if not wp_id or wp_id in state['accepted']:continue
        try:g._current_contract(state,packet)
        except Rejected:continue
        rank=(packet.get('id',''),binding['packet_ref']['path'],ref['path'])
        if wp_id not in latest or rank>latest[wp_id][0]:latest[wp_id]=(rank,ref,binding)
    out=[]
    for wp_id,(_rank,_ref,binding) in sorted(latest.items()):
        receipt=binding['receipt'];dispatch_id=receipt['dispatch_id']
        source_ref=state['current_candidates'].get(wp_id) or state['latest_sources'].get(wp_id)
        if not source_ref or receipt.get('fresh_context') is not False:continue
        source_binding=g.files.get(g.files.get(source_ref)['binding_ref'])
        if source_binding['receipt']['session_id']!=receipt.get('session_id'):continue
        if g.imported_dispatch_ref(dispatch_id) is None and dispatch_id in active|succeeded:out.append(dispatch_id)
    return out


def _incomplete_owner_action(g,state,view,dispatch_id):
    """Turn one host-proved no-delivery completion into a same-session resume."""
    if dispatch_id not in context_wait_dispatches(g,view):
        raise Rejected('no-delivery continuation is not the newest current same-session Owner context',
                       code='OWNER_CONTEXT_COMPLETION_NOT_CURRENT')
    binding_ref=g.files.named('bindings',dispatch_id)
    if binding_ref is None:raise Rejected('no-delivery continuation binding is missing')
    binding=g.files.get(binding_ref);receipt=binding['receipt'];packet_ref=binding['packet_ref'];packet=g.files.get(packet_ref)
    active={item['dispatch_id'] for item in view.get('active_dispatches',[])}
    settled={item['dispatch_id']:item.get('outcome') for item in view.get('settled_dispatches',[])}
    if (binding['role'] not in OWNERS or receipt.get('fresh_context') is not False or
            dispatch_id in active or settled.get(dispatch_id)!='succeeded' or
            g.imported_dispatch_ref(dispatch_id) is not None):
        raise Rejected('no-delivery continuation lacks exact settled context-only proof',
                       code='OWNER_CONTEXT_COMPLETION_UNVERIFIED')
    wp_id=packet['wp_id'];instruction=(
        f'The host completed context-only Dispatch `{dispatch_id}` for exact packet `{packet_ref["path"]}` '
        f'(digest {packet_ref["sha256"]}) without a MATS delivery/event. Resume the same retained Owner session '
        'and continue the current workspace through a verified candidate or a concrete external, authority, or '
        'tool blocker. Do not reload the full initialization prompt. Treat partial implementation, prerequisite '
        'tests, and progress narration as unfinished work, not as a candidate.')
    return {'status':'READY','reason_code':'OWNER_CONTEXT_TURN_RESUME','_kind':'dispatch',
            'operation':'owner','wp':wp_id,'continue_owner':True,'cyber':bool(packet.get('cyber',False)),
            'instructions':instruction,'source_ref':binding_ref,
            'next_operation':{'command':'wait','actor':'control'}}


def _review_action(g,state,wp_id,candidate_ref,role,review_ref,review):
    outcome=review['result']['outcome']
    if outcome=='fix_local':
        return {'status':'READY','reason_code':role.upper()+'_FIX_LOCAL','_kind':'dispatch','operation':'owner','wp':wp_id,
                'continue_owner':True,'instructions':_source_instruction(role.upper()+' fix_local',review_ref),
                'next_operation':{'command':'dispatch','operation':'owner','wp':wp_id,'continue_owner':True,'source_ref':review_ref['path']}}
    if outcome=='plan_conflict':
        return {'status':'READY','reason_code':'PLAN_CONFLICT','_kind':'plan_conflict','operation':'planner','wp':wp_id,
                'source_ref':review_ref,'next_operation':{'command':'advance','source_ref':review_ref['path']}}
    if role=='review_r1' and outcome=='needs_synthesis':
        request_ref=review.get('side_request_ref')
        if not isinstance(request_ref,dict):
            return {'status':'BLOCKED','reason_code':'SYNTHESIS_REQUEST_MISSING','source_ref':review_ref}
        sides=_side_results(g,request_ref)
        if len(sides)>1:return {'status':'BLOCKED','reason_code':'AMBIGUOUS_SYNTHESIS_RESULT','source_ref':request_ref}
        if not sides:
            return {'status':'READY','reason_code':'SYNTHESIS_REQUIRED','_kind':'dispatch','operation':'synthesis','wp':wp_id,
                    'request_ref':request_ref,'next_operation':{'command':'dispatch','operation':'synthesis','wp':wp_id,'request':request_ref['path']}}
        side_ref,_side=sides[0]
        return {'status':'READY','reason_code':'SYNTHESIS_RETURN_TO_OWNER','_kind':'dispatch','operation':'owner','wp':wp_id,
                'continue_owner':True,'instructions':_source_instruction('Consume and verify the requested Synthesis result',side_ref),
                'next_operation':{'command':'dispatch','operation':'owner','wp':wp_id,'continue_owner':True,'source_ref':side_ref['path']}}
    if outcome not in {'pass','escalate_r2'}:
        return {'status':'BLOCKED','reason_code':'UNSUPPORTED_REVIEW_OUTCOME','source_ref':review_ref}
    return None


def _resume_owner_action(g,state):
    eligible=[]
    for work in state['plan']['work_packages']:
        wp_id=work['id']
        if wp_id in state['accepted'] or state['current_candidates'].get(wp_id):continue
        source_ref=state['latest_sources'].get(wp_id)
        if source_ref:eligible.append((wp_id,source_ref))
    if len(eligible)!=1:
        return {'status':'BLOCKED','reason_code':'OWNER_RESUME_NOT_UNIQUE',
                'detail':'Control-level resume requires exactly one unfinished Owner result'}
    wp_id,source_ref=eligible[0]
    return {'status':'READY','reason_code':'USER_RESUMED_OWNER','_kind':'dispatch','operation':'owner','wp':wp_id,
            'continue_owner':True,
            'instructions':_resume_instruction(source_ref),
            'source_ref':source_ref,
            'next_operation':{'command':'advance','resume_owner':True}}


def select_action(g,view,*,cyber=None,resume_owner=False,incomplete_dispatch=None):
    """Select one transition using canonical state plus one normalized native view."""
    state=g.state()
    if incomplete_dispatch is not None:
        return _incomplete_owner_action(g,state,view,incomplete_dispatch)
    if view['active_dispatches']:return _wait()
    pending=_pending_binding_action(g,view)
    if pending:return pending
    proposals=_pending_planner(g,state)
    if len(proposals)>1:return {'status':'BLOCKED','reason_code':'AMBIGUOUS_PLANNER_PROPOSAL','proposal_refs':[ref for ref,_ in proposals]}
    if proposals:
        ref,_value=proposals[0]
        return {'status':'READY','reason_code':'PLANNER_PROPOSAL_READY','_kind':'apply_plan','proposal_ref':ref,
                'next_operation':{'command':'apply-plan','proposal_ref':ref['path']}}
    if resume_owner:return _resume_owner_action(g,state)
    for work in state['plan']['work_packages']:
        wp_id=work['id']
        if wp_id in state['accepted']:continue
        candidate_ref=state['current_candidates'].get(wp_id)
        if candidate_ref:
            candidate,owner_binding,owner_packet=_candidate_context(g,candidate_ref);cyber=bool(owner_packet.get('cyber',False))
            r0_ref=g.files.named('r0',candidate_ref['sha256'])
            if r0_ref is None:
                return {'status':'READY','reason_code':'R0_REQUIRED','_kind':'r0','candidate_ref':candidate_ref,
                        'next_operation':{'command':'r0','candidate_ref':candidate_ref['path']}}
            if not g.files.get(r0_ref)['passed']:
                return {'status':'READY','reason_code':'R0_FIX_LOCAL','_kind':'dispatch','operation':'owner','wp':wp_id,
                        'continue_owner':True,'instructions':_source_instruction('R0 fix_local',r0_ref),
                        'next_operation':{'command':'dispatch','operation':'owner','wp':wp_id,'continue_owner':True,'source_ref':r0_ref['path']}}
            r1_ref=g.files.named('reviews',candidate_ref['sha256']+'-review_r1')
            if r1_ref is None:
                return {'status':'READY','reason_code':'R1_REQUIRED','_kind':'dispatch','operation':'review_r1','wp':wp_id,
                        'cyber':cyber,'worktree':owner_binding['receipt']['workspace_key'],
                        'next_operation':{'command':'dispatch','operation':'review_r1','wp':wp_id}}
            r1=g.files.get(r1_ref);action=_review_action(g,state,wp_id,candidate_ref,'review_r1',r1_ref,r1)
            if action:return {**action,'cyber':cyber,'worktree':owner_binding['receipt']['workspace_key']}
            need_r2=g.needs_r2(candidate,state,r1)
            if need_r2:
                r2_ref=g.files.named('reviews',candidate_ref['sha256']+'-review_r2')
                if r2_ref is None:
                    return {'status':'READY','reason_code':'R2_REQUIRED','_kind':'dispatch','operation':'review_r2','wp':wp_id,
                            'cyber':cyber,'worktree':owner_binding['receipt']['workspace_key'],
                            'next_operation':{'command':'dispatch','operation':'review_r2','wp':wp_id}}
                r2=g.files.get(r2_ref);action=_review_action(g,state,wp_id,candidate_ref,'review_r2',r2_ref,r2)
                if action:return {**action,'cyber':cyber,'worktree':owner_binding['receipt']['workspace_key']}
            return {'status':'READY','reason_code':'ACCEPT_READY','_kind':'accept','wp':wp_id,
                    'next_operation':{'command':'accept','wp':wp_id}}
        latest_ref=state['latest_sources'].get(wp_id)
        if latest_ref:
            latest=g.files.get(latest_ref);result=latest.get('result',{});memo=result.get('source_memo',{})
            question=memo.get('decision_requested') if isinstance(memo,dict) else ''
            return {'status':'NEEDS_DECISION','reason_code':'OWNER_RESULT_NOT_CANDIDATE','wp':wp_id,
                    'source_ref':latest_ref,'question':question or None,'unresolved':result.get('unresolved',[]),
                    'unknowns':memo.get('unknowns',[]) if isinstance(memo,dict) else []}
        if all(dep in state['accepted'] for dep in work['dependencies']):
            if cyber is None:
                return {'status':'NEEDS_DECISION','reason_code':'CYBER_CLASSIFICATION_REQUIRED','wp':wp_id,
                        'question':'Does this WP require adversarial cybersecurity reasoning?',
                        'choices':[{'id':'cyber','next_operation':{'command':'advance','cyber':True}},
                                   {'id':'non_cyber','next_operation':{'command':'advance','cyber':False}}]}
            return {'status':'READY','reason_code':'OWNER_REQUIRED','_kind':'dispatch','operation':'owner','wp':wp_id,'cyber':bool(cyber),
                    'next_operation':{'command':'dispatch','operation':'owner','wp':wp_id,'cyber':bool(cyber)}}
    if len(state['accepted'])==len(state['plan']['work_packages']):return {'status':'DONE','reason_code':'AUTHORIZED_WORK_COMPLETE'}
    return {'status':'BLOCKED','reason_code':'NO_ELIGIBLE_WORK_PACKAGE'}


def _staged_bindings(g):
    root=g.files.root/'tmp'/'completions'
    if not root.exists():return []
    out=[]
    for path in sorted(root.glob('*.yaml')):
        record=load(path);ref=record.get('binding_ref') if isinstance(record,dict) else None
        if isinstance(ref,dict):out.append(ref)
    return out


def advance(g,*,cli='orca',cyber=None,resume_owner=False,incomplete_dispatch=None,max_steps=16,dry_run=False):
    trace=[]
    for _step in range(max_steps):
        staged=_staged_bindings(g)
        if staged:
            if dry_run:return {'status':'READY','reason_code':'RESULT_IMPORT_READY','next_operation':{'command':'result','binding_ref':staged[0]['path']},'trace':trace}
            for binding_ref in staged:
                if not g.files.completion_event_path(g.files.get(binding_ref)['receipt']['dispatch_id']).exists():continue
                result=process_staged_result(g,binding_ref,cli);trace.append({'operation':'result','binding_ref':binding_ref['path'],'result_ref':result['result_ref']['path']})
                if result.get('release_retry'):
                    return {'status':'BLOCKED','reason_code':'NATIVE_RELEASE_UNCONFIRMED','next_operation':{'command':'result','binding_ref':binding_ref['path']},'trace':trace}
                if result.get('acknowledgement_retry'):
                    return {'status':'BLOCKED','reason_code':'NATIVE_ACK_UNCONFIRMED','next_operation':{'command':'result','binding_ref':binding_ref['path']},'trace':trace}
            remaining=_staged_bindings(g)
            if remaining:
                event=load(g.files.completion_event_path(g.files.get(remaining[0])['receipt']['dispatch_id']))
                if event.get('batch_has_other_events'):
                    return {'status':'NEEDS_DECISION','reason_code':'NON_COMPLETION_EVENTS_PENDING','delivery_id':event.get('delivery_id'),'trace':trace}
            continue
        try:view=capture_runtime_view(g,cli,materialize=not dry_run)[0]
        except (Rejected,OSError,ValueError) as exc:
            return {'status':'BLOCKED',**rejection_payload(exc),'trace':trace}
        action=select_action(g,view,cyber=cyber,resume_owner=resume_owner,incomplete_dispatch=incomplete_dispatch)
        if dry_run:return {**_public(action),'trace':trace}
        kind=action.get('_kind')
        if kind is None:return {**_public(action),'trace':trace}
        try:
            if kind=='r0':
                ref=g.r0(action['candidate_ref']);trace.append({'operation':'r0','result_ref':ref['path']});continue
            if kind=='apply_plan':
                result=apply_plan_with_mechanical_owner_release(g,action['proposal_ref'],view,cli);trace.append({'operation':'apply-plan',**result});continue
            if kind=='accept':
                result=accept_with_mechanical_owner_release(g,action['wp'],view,cli);trace.append({'operation':'accept','wp':action['wp'],'owner_session_released':bool(result.get('owner_session_released'))});continue
            if kind=='plan_conflict':
                action={**action,'_kind':'dispatch','request_ref':g.planning_request_from_conflict(action['source_ref'])}
                kind='dispatch'
            if kind=='retry':
                launched=spawn(g,retry_packet=action['packet_ref'],cli=cli,dry_run=False)
            elif kind=='dispatch':
                launched=spawn(g,operation=action['operation'],wp=action.get('wp'),request=(action.get('request_ref') or {}).get('path'),
                               worktree=action.get('worktree','current'),cli=cli,instructions=action.get('instructions',''),
                               continue_owner=bool(action.get('continue_owner')),cyber=bool(action.get('cyber',cyber)),dry_run=False)
            else:raise Rejected('unknown deterministic advancement operation',code='ADVANCE_INTERNAL_ERROR')
            public=public_dispatch_result(launched);trace.append({'operation':'dispatch','dispatch_id':public.get('dispatch_id'),'role':public.get('role')})
            return {**_wait('WORKER_DISPATCHED'),'dispatch':public,'trace':trace}
        except (Rejected,OSError,ValueError,KeyError,TypeError) as exc:
            return {'status':'BLOCKED',**rejection_payload(exc),'attempted_action':_public(action),'trace':trace}
    return {'status':'READY','reason_code':'ADVANCE_STEP_LIMIT','next_operation':{'command':'advance'},'trace':trace}


def main(argv=None):
    ap=argparse.ArgumentParser(description='Advance deterministic MATS transitions until a worker wait, semantic decision, tool block, completion, or step limit.')
    ap.add_argument('--repo',default='.');ap.add_argument('--cli',default='orca',help=argparse.SUPPRESS)
    classification=ap.add_mutually_exclusive_group()
    classification.add_argument('-cyber','--cyber',dest='cyber',action='store_const',const=True,help='classify a newly selected Owner as adversarial cybersecurity work')
    classification.add_argument('--non-cyber',dest='cyber',action='store_const',const=False,help='classify a newly selected Owner as non-cybersecurity work')
    ap.set_defaults(cyber=None)
    ap.add_argument('--resume-owner',action='store_true',help='consume a user Control-level decision to resume the sole unfinished Owner; never forward the user text')
    ap.add_argument('--max-steps',type=int,default=16);ap.add_argument('--dry-run',action='store_true',help='select only; create no packet, task, delivery or state transition')
    a=ap.parse_args(argv)
    try:
        if not 1<=a.max_steps<=64:raise Rejected('--max-steps must be 1..64',code='INVALID_ADVANCE_LIMIT')
        emit_utf8(advance(Guards(a.repo),cli=a.cli,cyber=a.cyber,resume_owner=a.resume_owner,max_steps=a.max_steps,dry_run=a.dry_run));return 0
    except (Rejected,OSError,ValueError,KeyError,TypeError) as exc:
        emit_utf8(rejection_payload(exc),error=True);return 2
