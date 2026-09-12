"""Strict contracts and semantic dependency invariants, not a process state machine."""
from functools import lru_cache
import copy
from minischema import check_catalog, validate as schema_validate
from common import ROOT, Rejected, digest, identifier, load, relative

@lru_cache(maxsize=1)
def catalog():
    s = load(ROOT / 'schemas/contracts.schema.yaml')
    check_catalog(s)
    return s

def validate(kind, value):
    s = catalog()
    if kind not in s['$defs']:
        raise Rejected('unknown contract: ' + kind)
    schema_validate(s, kind, value)
    if kind == 'review' and value['outcome'] == 'pass':
        if any(f['severity'] in {'blocker','major'} and not f['resolved'] for f in value['findings']):
            raise Rejected('PASS with unresolved major/blocker')
    if kind == 'result':
        if value['status'] == 'candidate' and value['unresolved']:
            raise Rejected('candidate cannot leave material unresolved items')
        if value['status'] == 'plan_conflict' and not value['source_memo']['decision_requested'].strip():
            raise Rejected('plan_conflict requires a source decision request')
    if kind == 'side_result':
        if value['coverage']['examined'] > value['coverage']['total']:
            raise Rejected('invalid coverage')

def index(plan):
    return {w['id']:w for w in plan['work_packages']}

def planner_contract_checklist(project, plan, request, approved_checks):
    """Machine-derived Planner output invariants that prose/schema alone cannot convey.

    Keep this list aligned with validate_project_plan/materialize_planner_result/patch_impact.
    It is injected into every Planner packet so an expensive Planner sees cross-field rules
    before producing output.
    """
    bootstrap = request['reason'] == 'bootstrap'
    scoped = [c for c in project['commitments'] if c['scope'] == 'scoped']
    coverage_map = {
        'global_commitment_ids': sorted(c['id'] for c in project['commitments'] if c['scope'] == 'global'),
        'scoped_applies_to': {c['id']: sorted(c['applies_to']) for c in scoped},
        'current_expected_depends_on_commitments': {
            w['id']: sorted(c['id'] for c in scoped if w['id'] in c['applies_to'])
            for w in plan['work_packages']
        },
        'meaning': 'This is the current materialized map, not permission to freeze it. If the proposal changes scoped commitments, recompute the same relation in the proposed target.',
    }
    return {
        'authority': 'Contract items are generated from current Guard semantics; planning_quality items are stable Planner policy. Cross-check both before return.',
        'expected_mode': 'full' if bootstrap else 'patch',
        'base_plan_version': plan['version'],
        'target_plan_version': plan['version'] + 1,
        'identity': {'project_id': project['project_id'], 'current_plan_id': plan['plan_id'], 'mechanical_target_milestone_id': request.get('target_milestone_id')},
        'commitment_coverage': [
            'Global commitments have applies_to: [] and apply implicitly to every WP.',
            'A global commitment ID MUST NOT appear in any WP depends_on_commitments.',
            'A scoped commitment MUST have non-empty applies_to containing only existing WP IDs.',
            'For each WP, depends_on_commitments MUST equal exactly the scoped commitment IDs whose applies_to contains that WP; no more and no fewer.',
        ],
        'current_commitment_coverage_map': coverage_map,
        'planning_quality': [
            'Create coarse ownership Work Packages with independently meaningful semantic outcomes; do not split by file, function, command, or ordinary inspect/edit/test step.',
            'Keep local investigation, experiments, edits, debugging and focused tests inside the responsible Owner WP unless they change another WP contract or project commitment.',
            'Keep authority_role fixed as Research or Engineering and set specialty to the concise domain identity. Research owns evidence/decision outcomes; Engineering owns repository changes and tests. Split mixed work only when each side has an independently meaningful outcome.',
            'A qualification/validation WP may measure, package and report evidence but MUST NOT become an open-ended substantive implementation loop; route new code faults back to an Engineering remediation owner or a new plan occasion when boundaries change.',
            'Do not create a technical WP merely to represent waiting for one external/user action; require an owner WP only when evidence preparation/interpretation or another coherent semantic outcome is actually needed.',
            'Run counts, durations, exact thresholds and similar test procedure details invented by Planner remain proposed validation procedure/checks unless the user/source evidence explicitly makes them project commitments.',
        ],
        'wp_contract': [
            'Every dependency names an existing WP and the dependency graph is acyclic.',
            'Engineering WPs require non-empty scope.paths and at least one required_check.',
            'scope.paths are canonical POSIX relative paths and never include .task or .git.',
            'scope.refs are plan-time seed evidence and navigation advice, not runtime read permissions. Write path strings; the finalizer pins them. Read-only logs/evidence need no grant or plan patch.',
            'required_checks may use only approved check IDs supplied below.',
            'required_skills contains only mandatory methodology skills, not ordinary auto-discovered skills.',
            'specialty is descriptive domain identity only; it never changes authority, model, effort, scope, review or acceptance.',
            'Use interface_specs only on an Engineering WP when an architecture-bearing interface must survive Planner-to-Owner handoff. Include exact declarations and semantic obligations, never function bodies or routine local design.',
            'A required interface is exact; an incompatible Owner returns plan_conflict. An advisory interface may be adapted with cited evidence while preserving commitments and exit conditions.',
        ],
        'patch_rules': [
            'Bootstrap/full output returns a complete project and complete coarse plan at exactly target_plan_version.',
            'Runtime output is sparse patch-only; do not restate the full project/plan.',
            'Do not replace project_id. Do not write plan_id in a patch; Guard applies the request-pinned target_milestone_id mechanically.',
            'Accepted WPs whose contract/dependency closure is changed must be explicitly named in invalidate_accepted.',
        ],
        'approved_required_checks': sorted(approved_checks),
        'repair': ({
            'active': True,
            'occasion_is_immutable': True,
            'editing_rule': 'The generated semantic form is prefilled from the exact rejected proposal. Change only cells/rows required by the cited rejection; retain every unaffected decision.',
            'strategy_rule': 'Do not broaden scope, reset state, substitute a new design, add unrelated WPs/commitments or reinterpret the user directive. If the rejection cannot be repaired without doing so, return a concise conflict instead.',
            'output_rule': ('Bootstrap still materializes one complete first plan because no prior plan exists; repair it in the prefilled form.' if bootstrap else 'Return only the corrected sparse runtime patch; never restate the materialized project/plan.'),
        } if request.get('repair_of') else {
            'active': False,
            'editing_rule': 'This is the first proposal for the exact planning occasion.',
        }),
    }

def validate_project_plan(project, plan):
    validate('project', project); validate('plan', plan)
    if project['project_id'] != plan['project_id']:
        raise Rejected('project identity mismatch')
    wps = index(plan)
    if len(wps) != len(plan['work_packages']):
        raise Rejected('duplicate WP IDs')
    cs = {c['id']:c for c in project['commitments']}
    if len(cs) != len(project['commitments']):
        raise Rejected('duplicate commitment IDs')
    for c in cs.values():
        identifier(c['id'])
        if c['scope'] == 'global' and c['applies_to']:
            raise Rejected('global commitments implicitly cover all WPs')
        if c['scope'] == 'scoped' and (not c['applies_to'] or not set(c['applies_to']) <= set(wps)):
            raise Rejected('scoped commitment must explicitly cover existing WPs')
    for wid,w in wps.items():
        identifier(wid)
        for p in w['scope']['paths']:
            relative(p)
            if p in {'.task','.git'} or p.startswith(('.task/','.git/')):
                raise Rejected('worker write scope includes control/Git metadata')
        if w['owner_role'] == 'engineering' and (not w['scope']['paths'] or not w['required_checks']):
            raise Rejected('engineering requires write scope and at least one approved domain check')
        specs=w.get('interface_specs',[])
        if specs and w['owner_role']!='engineering':
            raise Rejected('interface_specs are valid only on Engineering WPs')
        spec_ids=[spec['id'] for spec in specs]
        if len(spec_ids)!=len(set(spec_ids)):
            raise Rejected('duplicate interface spec IDs')
        for spec in specs:
            identifier(spec['id']);target=relative(spec['target_path'])
            if target in {'.task','.git'} or target.startswith(('.task/','.git/')):
                raise Rejected('interface target includes control/Git metadata')
            if not any(target==root.rstrip('/') or target.startswith(root.rstrip('/') + '/') for root in w['scope']['paths']):
                raise Rejected('interface target must be inside WP write scope')
            for basis in spec['basis_paths']:
                path=relative(basis)
                if path in {'.task','.git'} or path.startswith(('.task/','.git/')):
                    raise Rejected('interface basis includes control/Git metadata')
        for key in ('dependencies','required_checks','depends_on_commitments','scope'):
            if key != 'scope' and len(w[key]) != len(set(w[key])):
                raise Rejected('duplicate list member: ' + key)
        if not set(w['dependencies']) <= set(wps):
            raise Rejected('unknown dependency')
        expected = {c['id'] for c in cs.values() if c['scope'] == 'scoped' and wid in c['applies_to']}
        if set(w['depends_on_commitments']) != expected:
            raise Rejected('commitment forward/reverse coverage mismatch')
    visiting, seen = set(), set()
    def visit(wid):
        if wid in visiting: raise Rejected('dependency cycle')
        if wid in seen: return
        visiting.add(wid)
        for dep in wps[wid]['dependencies']: visit(dep)
        visiting.remove(wid); seen.add(wid)
    for wid in wps: visit(wid)

def contract_digest(project, wp):
    # Global version is provenance; unrelated plan changes do not change this identity.
    cs = [c for c in project['commitments'] if c['scope'] == 'global' or c['id'] in wp['depends_on_commitments']]
    return digest({'wp':wp, 'goal':project['goal'], 'boundaries':project['boundaries'],
                   'commitments':sorted([{'id':c['id'],'statement':c['statement']} for c in cs],key=lambda c:c['id'])})

def closure(seeds, *plans):
    affected = set(seeds)
    changed = True
    while changed:
        changed = False
        for plan in plans:
            for w in plan['work_packages']:
                if w['id'] not in affected and set(w['dependencies']) & affected:
                    affected.add(w['id']); changed = True
    return affected

def patch_impact(old_project, old_plan, new_project, new_plan):
    validate_project_plan(new_project,new_plan)
    if old_project['project_id'] != new_project['project_id']:
        raise Rejected('project ID cannot be replaced')
    if new_plan['version'] != old_plan['version'] + 1:
        raise Rejected('plan version must advance exactly once')
    old, new = index(old_plan), index(new_plan)
    changed = set(old) ^ set(new)
    for wid in set(old) & set(new):
        if contract_digest(old_project,old[wid]) != contract_digest(new_project,new[wid]):
            changed.add(wid)
    return closure(changed,old_plan,new_plan)


def _apply_keyed(items, remove_ids, upserts, label):
    current = {x['id']: copy.deepcopy(x) for x in items}
    if len(current) != len(items):
        raise Rejected('duplicate ' + label + ' IDs before patch')
    remove_ids = list(remove_ids)
    upsert_ids = [x['id'] for x in upserts]
    if len(upsert_ids) != len(set(upsert_ids)):
        raise Rejected('duplicate ' + label + ' upsert IDs')
    overlap = set(remove_ids) & set(upsert_ids)
    if overlap:
        raise Rejected(label + ' cannot be removed and upserted in the same patch: ' + ','.join(sorted(overlap)))
    unknown = set(remove_ids) - set(current)
    if unknown:
        raise Rejected('cannot remove unknown ' + label + ': ' + ','.join(sorted(unknown)))
    for rid in remove_ids:
        current.pop(rid)
    for obj in upserts:
        current[obj['id']] = copy.deepcopy(obj)
    # Keep existing relative order when possible; append genuinely new IDs in patch order.
    ordered = [x['id'] for x in items if x['id'] in current and x['id'] not in set(upsert_ids)]
    ordered += upsert_ids
    return [current[i] for i in ordered]

def materialize_planner_result(old_project, old_plan, result):
    """Return a complete proposed project/plan from a validated Planner result.

    Bootstrap may return a full target. Runtime Planner calls return sparse patches;
    plan version advancement is generated here rather than copied by the model.
    """
    validate('planner_result', result)
    if result['base_plan_version'] != old_plan['version']:
        raise Rejected('Planner result base version does not match current plan')
    if result['mode'] == 'full':
        new_project = copy.deepcopy(result['project'])
        new_plan = copy.deepcopy(result['plan'])
    else:
        new_project = copy.deepcopy(old_project)
        new_plan = copy.deepcopy(old_plan)
        pp = result['project_patch']
        for key, value in pp['set'].items():
            new_project[key] = copy.deepcopy(value)
        cp = pp['commitments']
        new_project['commitments'] = _apply_keyed(new_project['commitments'], cp['remove'], cp['upsert'], 'commitment')
        wp = result['plan_patch']['work_packages']
        new_plan['work_packages'] = _apply_keyed(new_plan['work_packages'], wp['remove'], wp['upsert'], 'work package')
        new_plan['version'] = old_plan['version'] + 1
    validate_project_plan(new_project, new_plan)
    if new_plan['version'] != old_plan['version'] + 1:
        raise Rejected('Planner target plan version must advance exactly once')
    return new_project, new_plan
