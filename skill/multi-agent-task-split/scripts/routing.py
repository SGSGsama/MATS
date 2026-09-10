"""Fixed semantic role routing. No difficulty score or runtime scheduling loop."""
from pathlib import Path
from common import Rejected, identifier, require_fields
from contracts import validate

ROLES = {'control','research','engineering','review_r1','luna_aux','synthesis','review_r2','planner'}
OWNERS = {'research','engineering'}
AUX_CLASSES = {'bulk_index','candidate_search','structure_extract','event_normalize','result_cluster','test_triage','diff_manifest'}
SYNTHESIS_CLASSES = {'adjudication','causal_model','cross_evidence_synthesis','discriminating_experiment'}
POLICY_ID = 'fixed-semantic-v17'
FIXED_BINDINGS = {
    'research': {'model':'gpt-5.6-terra','reasoning_effort':'high'},
    'engineering': {'model':'gpt-5.6-terra','reasoning_effort':'high'},
    'review_r1': {'model':'gpt-5.6-terra','reasoning_effort':'high'},
    'luna_aux': {'model':'gpt-5.6-luna','reasoning_effort':'max'},
    'synthesis': {'model':'gpt-5.6-sol','reasoning_effort':'high'},
    'review_r2': {'model':'gpt-5.6-sol','reasoning_effort':'high'},
    'planner': {'model':'gpt-6-astra','reasoning_effort':'xhigh'},
    'control': {'model':'gpt-5.6-luna','reasoning_effort':'max'},
}
CYBER_REPLACED_MODEL = 'gpt-5.6-sol'
CYBER_PRIMARY_MODEL = 'gpt-daybreak-blue-latest'
R2_TRIGGER_TAGS = frozenset({
    'architectural_refactor',
    'milestone_integration',
    'cross_module_contract',
    'public_api_change',
    'persistent_schema_change',
    'protocol_semantics',
    'end_to_end_invariant',
    'state_or_ownership_invariant',
    'failure_recovery_invariant',
    'cross_platform_contract',
    'cryptographic_contract',
})

def validate_policy(p):
    if isinstance(p,dict) and 'structural_paths' in p:
        raise Rejected('retired structural_paths policy requires explicit user-directed migration',code='TASK_MIGRATION_REQUIRED')
    require_fields(p,{'schema_version','policy_id','bindings','packet_limits','budget_mode','evidence_roots','checks'})
    if p['schema_version'] != 9 or p['policy_id'] != POLICY_ID or set(p['bindings']) != ROLES or set(p['packet_limits']) != ROLES:
        raise Rejected('invalid fixed role catalog')
    if p['bindings'] != FIXED_BINDINGS:
        raise Rejected('fixed role bindings changed; models and effort are launcher-owned')
    if any(type(v) is not int or v <= 0 for v in p['packet_limits'].values()):
        raise Rejected('packet limits must be positive byte counts')
    if p['budget_mode'] != 'observe':
        raise Rejected('this release observes usage; hard spend enforcement must be supplied by the native host')
    if not isinstance(p['evidence_roots'],list) or any(not isinstance(x,str) or not x or not Path(x).is_absolute() for x in p['evidence_roots']):
        raise Rejected('evidence_roots must contain only absolute host paths')
    if len(p['evidence_roots']) != len(set(p['evidence_roots'])):
        raise Rejected('duplicate evidence root')
    if not isinstance(p['checks'],dict):
        raise Rejected('checks must be an operator-owned catalog')
    for key,spec in p['checks'].items():
        identifier(key);require_fields(spec,{'argv'}, {'timeout_seconds'})
        argv=spec['argv'];timeout=spec.get('timeout_seconds',60)
        if not isinstance(argv,list) or not argv or any(not isinstance(x,str) or not x for x in argv):
            raise Rejected('check argv must be a non-empty argument array')
        if type(timeout) is not int or not 1 <= timeout <= 600:
            raise Rejected('check timeout must be an integer from 1 through 600 seconds')


def validate_operator(value):
    validate('operator_control', value)
    caps=value['caps']
    if any(v is not None and (type(v) is not int or v <= 0) for v in caps.values()):
        raise Rejected('optional operator caps must be null or positive integers')
    return value

def route_side(request):
    validate('side_request',request)
    if request['affected_commitments']:
        raise Rejected('commitment change goes directly to Planner, not through Sol/Luna')
    role = 'luna_aux' if request['class'] in AUX_CLASSES else 'synthesis'
    if request['kind'] != role: raise Rejected('semantic class/role mismatch')
    if not request['verification_plan'].strip() or not request['benefit'].strip():
        raise Rejected('side call needs a verification plan and expected work saved')
    if role == 'synthesis' and (not request['attempted'] or not request['evidence']):
        raise Rejected('synthesis needs prior local work and pinned evidence')
    return role

def next_review(outcome):
    # A role is not an escalation ladder; each result has one semantic next action.
    return {'pass':'accept_or_r2', 'fix_local':'owner', 'needs_synthesis':'synthesis_then_owner',
            'escalate_r2':'review_r2', 'plan_conflict':'planner'}[outcome]

def fixed_binding(policy,role):
    if role not in ROLES: raise Rejected('unknown role')
    return dict(policy['bindings'][role])

def dispatch_bindings(policy,role,*,cyber=False):
    """Resolve the launcher-owned primary and the sole permitted fallback.

    ``cyber`` is a semantic task classification supplied by Control, never a
    model override. It only replaces roles whose fixed model is Sol and keeps
    that role's configured effort unchanged.
    """
    if type(cyber) is not bool: raise Rejected('cyber classification must be boolean')
    base=fixed_binding(policy,role)
    if cyber and base['model']==CYBER_REPLACED_MODEL:
        return {'primary':{'model':CYBER_PRIMARY_MODEL,'reasoning_effort':base['reasoning_effort']},'fallback':base}
    return {'primary':base,'fallback':None}

def launch_argv(policy,role,task_id,worktree,*,cli='orca',terminal=None,reuse_receipt=None,cyber=False,fallback=False):
    # Generate fixed native launch arguments for the Skill-local `bin/mats dispatch` bridge. Control uses it for all roles; an authorized Owner may use the same launcher only for source-authored Luna Aux when native depth permits.
    if role=='control': raise Rejected('Control is a native root/full-handoff session, not a supervised child coordinator')
    args=[cli,'orchestration','worker-start','--task',task_id]
    if terminal:
        if fallback: raise Rejected('same-owner continuation has no model fallback launch')
        plans=dispatch_bindings(policy,role,cyber=cyber)
        permitted=[value for value in (plans['primary'],plans['fallback']) if value is not None]
        if role not in OWNERS or not reuse_receipt or reuse_receipt['effective'] not in permitted:
            raise Rejected('only the same attested owner may reuse a terminal; reviewers/side roles are fresh')
        if not isinstance(reuse_receipt.get('workspace_key'),str) or not reuse_receipt['workspace_key']:
            raise Rejected('same-owner continuation requires the attested workspace key')
        args += ['--worktree','id:'+reuse_receipt['workspace_key'],'--terminal',terminal]
    else:
        plan=dispatch_bindings(policy,role,cyber=cyber)
        b=plan['fallback'] if fallback else plan['primary']
        if b is None: raise Rejected('fallback launch is not defined for this role/classification')
        args += ['--worktree',worktree,'--agent','codex','--model',b['model'],'--effort',b['reasoning_effort']]
    return args+['--json']

def admission(view,project_id,run_id,role,wp_id,workspace_key,access,*,reuse_session=None,max_parallel=None):
    validate('runtime_view',view)
    if view['project_id'] != project_id or view['run_id'] != run_id:
        raise Rejected('runtime view belongs to another project/run')
    if role not in ROLES or access not in {'write','read_live','read_snapshot'}:
        raise Rejected('unknown role/access')
    if role not in OWNERS and access == 'write': raise Rejected('only owners have domain write access')
    if max_parallel and len(view['active_dispatches']) >= max_parallel:
        raise Rejected('operator parallelism cap; do not change models')
    if role in OWNERS and any(d['wp_id'] == wp_id and d['role'] in OWNERS for d in view['active_dispatches']):
        raise Rejected('same WP already has an active owner')
    reuse_seen=False
    for u in view['workspace_users']:
        if u['session_id'] == reuse_session:
            if u['wp_id'] != wp_id or role not in OWNERS or u['workspace_key'] != workspace_key:
                raise Rejected('reuse must be same WP and workspace')
            reuse_seen=True
            continue
        if u['workspace_key'] != workspace_key: continue
        if (access == 'write' and u['access'] != 'read_snapshot') or (access == 'read_live' and u['access'] == 'write'):
            raise Rejected('workspace conflict: isolate a worktree/snapshot or release its writer/readers')
    if reuse_session is not None and not reuse_seen:
        raise Rejected('retained Owner session is absent from the fresh runtime view')
    return {'eligible':True,'lifecycle_authority':'Orca','role':role}

def require_drained(view,affected):
    validate('runtime_view',view)
    if any(d['wp_id'] in affected or (d['wp_id'] is None and d['role'] != 'planner') for d in view['active_dispatches']):
        raise Rejected('affected closure has active native dispatches; drain only that closure',code='AFFECTED_DISPATCH_ACTIVE')
    if any(u['access'] == 'write' and (u['wp_id'] in affected or u['wp_id'] is None) for u in view['workspace_users']):
        raise Rejected('affected writer terminal is still live; worker_done is not writer release',code='OWNER_RELEASE_REQUIRED')
