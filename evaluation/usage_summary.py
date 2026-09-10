#!/usr/bin/env python3
"""Observe cumulative worker and Control usage without double-counting context loads."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'skill/multi-agent-task-split/scripts'))
from common import Rejected,require_fields,load,encode

def _complete(row,field):
    value=row.get(field)
    if type(value) is not bool:raise Rejected(f'{field} must be Boolean')
    return value

def _usage_rows(rows,id_field,complete_field,optional=frozenset()):
    if not isinstance(rows,list):raise Rejected(f'{id_field} usage must be a list')
    seen={}
    for r in rows:
        require_fields(r,{id_field,'model','input_tokens','output_tokens','reasoning_tokens','cost_microusd',complete_field},optional)
        _complete(r,complete_field)
        for key in ('input_tokens','output_tokens','reasoning_tokens','cost_microusd'):
            if r[key] is not None and (type(r[key]) is not int or r[key]<0):raise Rejected('usage must be null or nonnegative integers')
        if r['reasoning_tokens'] is not None and r['output_tokens'] is not None and r['reasoning_tokens']>r['output_tokens']:
            raise Rejected('reasoning is an output subset, not additional tokens')
        old=seen.get(r[id_field])
        if old and old!=r:raise Rejected('conflicting cumulative totals: reconcile them, do not sum snapshots')
        seen[r[id_field]]=r
    return list(seen.values())

def _context(control_rows):
    totals={};events=0;missing=[]
    for row in control_rows:
        loads=row.get('context_loads')
        if not isinstance(loads,list):
            missing.append(row['session_id']);continue
        seen={};classes=set();exact=True
        for item in loads:
            require_fields(item,{'load_id','component','input_tokens','complete','included_in_control_input'})
            if not isinstance(item['load_id'],str) or not item['load_id']:raise Rejected('context load_id must be nonempty')
            if not isinstance(item['component'],str) or ':' not in item['component']:raise Rejected('context component must use class:name')
            if type(item['complete']) is not bool or type(item['included_in_control_input']) is not bool:raise Rejected('context flags must be Boolean')
            if not item['included_in_control_input']:raise Rejected('context loads are attribution inside Control input, never additive usage')
            value=item['input_tokens']
            if value is not None and (type(value) is not int or value<0):raise Rejected('context input_tokens must be null or nonnegative integer')
            old=seen.get(item['load_id'])
            if old and old!=item:raise Rejected('conflicting context load observations')
            if old:continue
            seen[item['load_id']]=item;events+=1
            cls=item['component'].split(':',1)[0];classes.add(cls)
            if not item['complete'] or value is None:exact=False
            else:totals[item['component']]=totals.get(item['component'],0)+value
        if not {'mats','orca'}<=classes or not exact:missing.append(row['session_id'])
        elif row['input_tokens'] is not None and sum(x['input_tokens'] for x in seen.values())>row['input_tokens']:
            raise Rejected('attributed context exceeds Control input total')
    return totals,events,sorted(set(missing))

def summarize(value):
    managed=isinstance(value,dict)
    if managed:
        require_fields(value,{'dispatches','control_sessions'})
        dispatches=_usage_rows(value['dispatches'],'dispatch_id','complete_native_loop')
        controls=_usage_rows(value['control_sessions'],'session_id','complete_control_session',{'context_loads'})
    elif isinstance(value,list):
        dispatches=_usage_rows(value,'dispatch_id','complete_native_loop');controls=[]
    else:raise Rejected('usage input must be a legacy dispatch list or managed evaluation mapping')
    exact_dispatches=[r for r in dispatches if r['complete_native_loop'] and all(r[k] is not None for k in ('input_tokens','output_tokens','cost_microusd'))]
    exact_controls=[r for r in controls if r['complete_control_session'] and all(r[k] is not None for k in ('input_tokens','output_tokens','cost_microusd'))]
    context_totals,context_events,missing_context=_context(controls)
    rows=dispatches+controls;exact=exact_dispatches+exact_controls
    partial=[r for r in rows if r not in exact]
    return {'budget_mode':'observe','managed_evaluation':managed,'dispatches_observed':len(dispatches),'complete_usage_dispatches':len(exact_dispatches),
            'control_sessions_observed':len(controls),'complete_usage_control_sessions':len(exact_controls),
            'unknown_or_partial_dispatches':[r['dispatch_id'] for r in dispatches if r not in exact_dispatches],
            'unknown_or_partial_control_sessions':[r['session_id'] for r in controls if r not in exact_controls],
            'known_complete_tokens':sum(r['input_tokens']+r['output_tokens'] for r in exact),
            'known_complete_control_tokens':sum(r['input_tokens']+r['output_tokens'] for r in exact_controls),
            'known_complete_dispatch_tokens':sum(r['input_tokens']+r['output_tokens'] for r in exact_dispatches),
            'known_complete_cost_microusd':sum(r['cost_microusd'] for r in exact),
            'context_load_events_observed':context_events,'context_input_tokens_by_component':context_totals,
            'known_attributed_context_input_tokens':sum(context_totals.values()),
            'context_tokens_already_in_control_input':True,'context_tokens_added_again':False,
            'missing_or_incomplete_control_context':missing_context,
            'project_total_known':bool(rows) and not partial and (not managed or (bool(controls) and not missing_context)),
            'hard_spend_cap_enforced':False}

if __name__=='__main__':
    try:print(encode(summarize(load(sys.argv[1]))).decode(),end='')
    except (Rejected,OSError,IndexError) as exc:print(str(exc),file=sys.stderr);raise SystemExit(2)
