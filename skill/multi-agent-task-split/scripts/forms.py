"""Model-facing semantic forms; transaction contracts remain script-owned YAML.

The child edits a generated UTF-8 TSV table.  The packet-bound finalizer parses
only documented semantic rows, materializes identities/hashes/snapshots, validates
the normal contract, then replaces the table with canonical YAML.  This keeps
reproducible bookkeeping out of model I/O without weakening the existing Guard.
"""
from __future__ import annotations

import copy
import csv
import io

from common import Rejected

MAGIC = 'MATS-FORM'
VERSION = '1'
KINDS = {
    'result', 'review', 'side_result', 'side_request_luna_aux',
    'side_request_synthesis', 'planning_request', 'planner_full', 'planner_patch',
}


def is_form_bytes(data: bytes) -> bool:
    return data.startswith((MAGIC + '\t').encode('utf-8')) or data.startswith(('\ufeff' + MAGIC + '\t').encode('utf-8'))


def _text(value):
    if value is None:
        return ''
    if isinstance(value, bool):
        return 'true' if value else 'false'
    return str(value)


def _emit(kind, comments, rows):
    if kind not in KINDS:
        raise Rejected('unknown semantic form kind: ' + str(kind))
    sink = io.StringIO(newline='')
    writer = csv.writer(sink, dialect='excel-tab', lineterminator='\n')
    writer.writerow([MAGIC, VERSION, kind])
    for comment in comments:
        writer.writerow(['# ' + comment])
    for row in rows:
        writer.writerow([_text(cell) for cell in row])
    return sink.getvalue().encode('utf-8')


def _paths(items):
    out = []
    for item in items or []:
        if isinstance(item, str):
            out.append(('evidence', item))
        elif isinstance(item, dict) and isinstance(item.get('manifest'), str):
            out.append(('evidence_manifest', item['manifest']))
        elif isinstance(item, dict) and isinstance(item.get('path'), str):
            out.append(('evidence', item['path']))
    return out


def _memo_rows(memo):
    memo = memo if isinstance(memo, dict) else {}
    rows = []
    for key, row_name in (
        ('claims', 'claim'), ('observations', 'observation'), ('unknowns', 'memo_unknown'),
        ('downstream_impact', 'downstream_impact'),
    ):
        rows.extend((row_name, value) for value in memo.get(key, []) if isinstance(value, str))
    if memo.get('decision_requested'):
        rows.append(('decision_requested', memo['decision_requested']))
    for row_name, value in _paths(memo.get('evidence_refs', [])):
        rows.append(('memo_manifest' if row_name == 'evidence_manifest' else 'memo_evidence', value))
    for ref in memo.get('source_refs',[]):
        path=ref.get('path') if isinstance(ref,dict) else ref
        if isinstance(path,str):rows.append(('memo_source',path))
    return rows


def _owner_form(prefill):
    value = prefill if isinstance(prefill, dict) else {}
    rows = [('status', value.get('status')), ('summary', value.get('summary')), ('impact', value.get('impact'))]
    rows += _paths(value.get('evidence', []))
    rows += [('unresolved', item) for item in value.get('unresolved', [])]
    rows += [('structural_tag', item) for item in value.get('structural_tags', [])]
    rows += _memo_rows(value.get('source_memo'))
    for number, item in enumerate(value.get('consumed_sides', []), 1):
        if not isinstance(item, dict):
            continue
        key = 'side' + str(number)
        ref = item.get('side_ref')
        path = ref.get('path') if isinstance(ref, dict) else ref
        rows.append(('consumed_side', key, path, item.get('disposition'), item.get('reason')))
        for row_name, evidence_path in _paths(item.get('verified_evidence', [])):
            rows.append(('consumed_manifest' if row_name == 'evidence_manifest' else 'consumed_evidence', key, evidence_path))
    return _emit('result', [
        'Fill column values; keep the header and row names. Add repeatable rows as needed.',
        'status is candidate, blocked, failed, or plan_conflict; native succeeded is not a semantic status. candidate means every WP exit condition is met.',
        'Rows: status, summary, impact, evidence/evidence_manifest, unresolved, structural_tag.',
        'Use evidence for ordinary files (including .sha256); evidence_manifest only names YAML from mats evidence.',
        'Memo rows: claim, observation, memo_unknown, downstream_impact, decision_requested, memo_evidence/memo_manifest, memo_source for .task results/reviews.',
        'Optional Aux rows: consumed_side <key> <side-result .task path> <disposition> <reason>; consumed_evidence/manifest <key> <path>.',
        'Do not add schema, snapshot, hashes, versions, binding IDs or other transaction fields.',
    ], rows)


def _review_form(prefill):
    value = prefill if isinstance(prefill, dict) else {}
    rows = [('outcome', value.get('outcome')), ('summary', value.get('summary'))]
    for number, finding in enumerate(value.get('findings', []), 1):
        if not isinstance(finding, dict):
            continue
        key = 'finding' + str(number)
        rows.append(('finding', key, finding.get('severity'), finding.get('resolved'), finding.get('detail')))
        for row_name, path in _paths(finding.get('evidence', [])):
            rows.append(('finding_manifest' if row_name == 'evidence_manifest' else 'finding_evidence', key, path))
    rows += _memo_rows(value.get('source_memo'))
    return _emit('review', [
        'Fill values; keep the header and row names. Add repeatable rows as needed.',
        'outcome is pass, fix_local, needs_synthesis, escalate_r2, or plan_conflict (R2 only uses pass/fix_local/plan_conflict).',
        'finding columns: key, severity, resolved(true/false), detail; attach evidence with the same key.',
        'Use *_evidence for ordinary files and *_manifest only for YAML from mats evidence. Memo rows are the same as Owner forms; memo_source cites .task results/reviews.',
        'Target digest, hashes, versions and schema are script-owned.',
    ], rows)


def _side_form(prefill):
    value = prefill if isinstance(prefill, dict) else {}
    coverage = value.get('coverage') if isinstance(value.get('coverage'), dict) else {}
    rows = [('status', value.get('status')), ('summary', value.get('summary'))]
    rows += _paths(value.get('evidence', []))
    rows += [('unknown', item) for item in value.get('unknowns', [])]
    rows.append(('coverage', coverage.get('examined'), coverage.get('total')))
    rows += [('excluded', item) for item in coverage.get('excluded', [])]
    rows += [('next_action', item) for item in value.get('proposed_next_actions', [])]
    return _emit('side_result', [
        'Fill values; keep the header and row names. Add repeatable rows as needed.',
        'status is done, blocked, or failed.',
        'coverage columns are examined and total integers. Use evidence for ordinary files and evidence_manifest only for YAML from mats evidence.',
        'Evidence hashes, versions and schema are script-owned.',
    ], rows)


def render_side_request_form(operation, *, prefill=None):
    if operation not in {'luna_aux','synthesis'}:
        raise Rejected('side request form operation must be luna_aux or synthesis')
    value=prefill if isinstance(prefill,dict) else {}
    rows=[('class',value.get('class')),('question',value.get('question'))]
    rows += [('current_finding',item) for item in value.get('current_findings',[])]
    rows += [('competing_explanation',item) for item in value.get('competing_explanations',[])]
    rows += [('attempted',item) for item in value.get('attempted',[])]
    rows += _paths(value.get('evidence',[]))
    rows += [('affected_commitment',item) for item in value.get('affected_commitments',[])]
    rows += [('requested_output',value.get('requested_output')),('verification_plan',value.get('verification_plan')),
             ('benefit',value.get('benefit')),('decision_key',value.get('decision_key'))]
    return _emit('side_request_'+operation,[
        'Fill semantic values only. The header fixes the requested operation; MATS generates schema/evidence hashes/versions.',
        'Repeatable rows: current_finding, competing_explanation, attempted, evidence/evidence_manifest, affected_commitment.',
        'Use evidence for ordinary files and evidence_manifest only for YAML from mats evidence.',
        'Required singleton rows: class, question, requested_output, verification_plan, benefit, decision_key.',
    ],rows)


def render_planning_request_form(*, prefill=None):
    """Render the sole Control-editable input for a non-bootstrap Planner occasion."""
    value=prefill if isinstance(prefill,dict) else {}
    rows=[('reason',value.get('reason')),('question',value.get('question'))]
    rows += [('source_path',item.get('path') if isinstance(item,dict) else item) for item in value.get('source_refs',[])]
    for item in value.get('directives',[]):
        if isinstance(item,dict):rows.append(('directive',item.get('id'),item.get('intent'),item.get('raw_text')))
    rows += [('affected_wp',item) for item in value.get('affected_wp_ids',[])]
    if value.get('target_milestone_id'):rows.append(('target_milestone',value['target_milestone_id']))
    return _emit('planning_request',[
        'Fill semantic cells only. Keep user/source directive text verbatim; do not add design choices to question.',
        'Rows: reason, question, source_path, directive <id> <intent> <raw_text>, affected_wp, optional target_milestone.',
        'MATS stores directives and generates the immutable request plus every internal ref/hash.',
    ],rows)


def _ref_paths(items):
    return [item.get('path') if isinstance(item, dict) else item for item in (items or []) if isinstance(item, (str, dict))]


def _commitment_rows(items, prefix):
    rows = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        cid = item.get('id')
        rows.append((prefix, cid, item.get('scope'), item.get('statement')))
        rows.extend((prefix + '_applies', cid, wid) for wid in item.get('applies_to', []))
    return rows


def _work_rows(items, prefix):
    rows = []
    child_names = {
        'constraints': 'constraint', 'exit_conditions': 'exit', 'dependencies': 'dependency',
        'required_skills': 'skill', 'required_checks': 'check',
        'depends_on_commitments': 'commitment',
    }
    for item in items or []:
        if not isinstance(item, dict):
            continue
        wid = item.get('id')
        rows.append((prefix, wid, item.get('owner_role'), item.get('specialty'), item.get('impact'),
                     item.get('review_policy'), item.get('title'), item.get('objective')))
        for field, suffix in child_names.items():
            rows.extend((prefix + '_' + suffix, wid, value) for value in item.get(field, []))
        scope = item.get('scope') if isinstance(item.get('scope'), dict) else {}
        rows.extend((prefix + '_scope_path', wid, value) for value in scope.get('paths', []))
        rows.extend((prefix + '_scope_ref', wid, value) for value in _ref_paths(scope.get('refs', [])))
    return rows


def _planner_full(packet, prefill):
    value = prefill if isinstance(prefill, dict) and prefill.get('mode') == 'full' else {}
    project = value.get('project') if isinstance(value.get('project'), dict) else copy.deepcopy(packet.get('project') or {})
    plan = value.get('plan') if isinstance(value.get('plan'), dict) else copy.deepcopy(packet.get('plan') or {})
    rows = [('reason', value.get('reason'))]
    rows += [('basis_path', path) for path in _ref_paths(value.get('basis_refs', []))]
    rows += [('invalidate', wid) for wid in value.get('invalidate_accepted', [])]
    rows += [('project_goal', project.get('goal')), ('project_phase', project.get('phase'))]
    for field, row_name in (
        ('boundaries', 'project_boundary'), ('strategic_risks', 'project_risk'),
        ('working_hypotheses', 'project_hypothesis'), ('open_questions', 'project_question'),
    ):
        rows.extend((row_name, item) for item in project.get(field, []))
    rows += _commitment_rows(project.get('commitments', []), 'commitment')
    rows += _work_rows(plan.get('work_packages', []), 'wp')
    return _emit('planner_full', _planner_comments(full=True), rows)


def _planner_patch(packet, prefill):
    value = prefill if isinstance(prefill, dict) and prefill.get('mode') == 'patch' else {}
    project_patch = value.get('project_patch') if isinstance(value.get('project_patch'), dict) else {}
    plan_patch = value.get('plan_patch') if isinstance(value.get('plan_patch'), dict) else {}
    set_value = project_patch.get('set') if isinstance(project_patch.get('set'), dict) else {}
    commitments = project_patch.get('commitments') if isinstance(project_patch.get('commitments'), dict) else {}
    packages = plan_patch.get('work_packages') if isinstance(plan_patch.get('work_packages'), dict) else {}
    rows = [('reason', value.get('reason'))]
    rows += [('basis_path', path) for path in _ref_paths(value.get('basis_refs', []))]
    rows += [('invalidate', wid) for wid in value.get('invalidate_accepted', [])]
    for field in ('goal', 'phase'):
        if field in set_value:
            rows.append(('project_set', field, set_value[field]))
    for field in ('boundaries', 'strategic_risks', 'working_hypotheses', 'open_questions'):
        if field in set_value:
            if set_value[field]:
                rows.extend(('project_list', field, item) for item in set_value[field])
            else:
                rows.append(('project_clear', field))
    rows += _commitment_rows(commitments.get('upsert', []), 'commitment_upsert')
    rows += [('commitment_remove', cid) for cid in commitments.get('remove', [])]
    rows += _work_rows(packages.get('upsert', []), 'wp_upsert')
    rows += [('wp_remove', wid) for wid in packages.get('remove', [])]
    return _emit('planner_patch', _planner_comments(full=False), rows)


def _planner_comments(*, full):
    mode = 'complete bootstrap target' if full else 'sparse runtime patch; omit unchanged project/WP rows'
    return [
        'This form is ' + mode + '. Mode, project/plan IDs, schema and plan version are script-owned.',
        'Core rows: reason, basis_path, invalidate. Runtime project rows: project_set/list/clear.',
        'Commitment rows: commitment[_upsert] <id> <global|scoped> <statement>; matching _applies rows; optional commitment_remove.',
        'WP row columns: id, owner_role, specialty, impact, review_policy, title, objective.',
        'WP child rows: *_constraint, *_exit, *_dependency, *_skill, *_scope_path, *_scope_ref, *_check, *_commitment.',
        'Paths only: the finalizer creates every internal reference, hash and version.',
    ]


def render_form(packet, *, prefill=None):
    role = packet.get('role')
    if role in {'research', 'engineering'}:
        return _owner_form(prefill)
    if role in {'review_r1', 'review_r2'}:
        return _review_form(prefill)
    if role in {'luna_aux', 'synthesis'}:
        return _side_form(prefill)
    if role == 'planner':
        return _planner_full(packet, prefill) if packet.get('request', {}).get('reason') == 'bootstrap' else _planner_patch(packet, prefill)
    raise Rejected('role has no semantic delivery form: ' + str(role))


def _read(data):
    try:
        text = data.decode('utf-8-sig')
    except UnicodeDecodeError as exc:
        raise Rejected('semantic form must be UTF-8') from exc
    try:
        rows = list(csv.reader(io.StringIO(text, newline=''), dialect='excel-tab'))
    except csv.Error as exc:
        raise Rejected('invalid semantic TSV form: ' + str(exc)) from exc
    if not rows or len(rows[0]) != 3 or rows[0][0] != MAGIC or rows[0][1] != VERSION or rows[0][2] not in KINDS:
        raise Rejected('invalid semantic form header')
    body = []
    for line, row in enumerate(rows[1:], 2):
        if not row or all(not cell.strip() for cell in row) or row[0].lstrip().startswith('#'):
            continue
        row = [cell.strip() for cell in row]
        body.append((line, row))
    return rows[0][2], body


def _arity(line, row, minimum, maximum=None):
    maximum = minimum if maximum is None else maximum
    if not minimum <= len(row) <= maximum:
        raise Rejected(f'form line {line} `{row[0]}` requires {minimum - 1}' + ('' if maximum == minimum else f'..{maximum - 1}') + ' value columns')


def _singleton(target, key, value, line):
    if key in target:
        raise Rejected(f'duplicate singleton form row `{key}` at line {line}')
    target[key] = value


def _memo_add(memo, kind, value):
    mapping = {'claim': 'claims', 'observation': 'observations', 'memo_unknown': 'unknowns', 'downstream_impact': 'downstream_impact'}
    if kind in mapping:
        memo[mapping[kind]].append(value)
    elif kind == 'decision_requested':
        if memo['decision_requested']:
            raise Rejected('duplicate decision_requested form row')
        memo['decision_requested'] = value
    elif kind == 'memo_evidence':
        memo['evidence_refs'].append(value)
    elif kind == 'memo_manifest':
        memo['evidence_refs'].append({'manifest': value})
    elif kind == 'memo_source':
        memo.setdefault('source_refs',[]).append(value)


def _memo():
    return {'claims': [], 'observations': [], 'unknowns': [], 'downstream_impact': [], 'decision_requested': '', 'evidence_refs': []}


def _parse_result(rows):
    out = {'evidence': [], 'unresolved': [], 'structural_tags': [], 'source_memo': _memo(), 'consumed_sides': []}
    singles = {}
    consumed = {}
    memo_names = {'claim', 'observation', 'memo_unknown', 'downstream_impact', 'decision_requested', 'memo_evidence', 'memo_manifest', 'memo_source'}
    for line, row in rows:
        kind = row[0]
        if kind in {'status', 'summary', 'impact'}:
            _arity(line, row, 2); _singleton(singles, kind, row[1], line)
            if kind=='status' and row[1] and row[1] not in {'candidate','blocked','failed','plan_conflict'}:
                raise Rejected(f'form line {line} status must be candidate, blocked, failed, or plan_conflict; native succeeded belongs only to worker_done')
            if kind=='impact' and row[1] and row[1] not in {'local','module','cross_boundary','unknown'}:
                raise Rejected(f'form line {line} impact must be local, module, cross_boundary, or unknown')
        elif kind in {'evidence', 'evidence_manifest', 'unresolved', 'structural_tag'}:
            _arity(line, row, 2)
            if kind == 'evidence': out['evidence'].append(row[1])
            elif kind == 'evidence_manifest': out['evidence'].append({'manifest': row[1]})
            elif kind == 'unresolved': out['unresolved'].append(row[1])
            else: out['structural_tags'].append(row[1])
        elif kind in memo_names:
            _arity(line, row, 2); _memo_add(out['source_memo'], kind, row[1])
        elif kind == 'consumed_side':
            _arity(line, row, 5)
            if row[1] in consumed: raise Rejected('duplicate consumed_side key: ' + row[1])
            consumed[row[1]] = {'side_ref': row[2], 'disposition': row[3], 'reason': row[4], 'verified_evidence': []}
        elif kind in {'consumed_evidence', 'consumed_manifest'}:
            _arity(line, row, 3)
            if row[1] not in consumed: raise Rejected('consumed evidence precedes/has unknown side key: ' + row[1])
            consumed[row[1]]['verified_evidence'].append(row[2] if kind == 'consumed_evidence' else {'manifest': row[2]})
        else:
            raise Rejected(f'unknown result form row `{kind}` at line {line}')
    out.update(singles); out['consumed_sides'] = list(consumed.values())
    return out


def _parse_review(rows):
    out = {'findings': [], 'source_memo': _memo()}; singles = {}; findings = {}
    memo_names = {'claim', 'observation', 'memo_unknown', 'downstream_impact', 'decision_requested', 'memo_evidence', 'memo_manifest', 'memo_source'}
    for line, row in rows:
        kind = row[0]
        if kind in {'outcome', 'summary'}:
            _arity(line, row, 2); _singleton(singles, kind, row[1], line)
            if kind=='outcome' and row[1] and row[1] not in {'pass','fix_local','needs_synthesis','escalate_r2','plan_conflict'}:
                raise Rejected(f'form line {line} outcome is not a supported review transition')
        elif kind == 'finding':
            _arity(line, row, 5)
            if row[1] in findings: raise Rejected('duplicate finding key: ' + row[1])
            if row[3].lower() not in {'true', 'false'}: raise Rejected(f'form line {line} finding resolved must be true or false')
            findings[row[1]] = {'severity': row[2], 'resolved': row[3].lower() == 'true', 'detail': row[4], 'evidence': []}
        elif kind in {'finding_evidence', 'finding_manifest'}:
            _arity(line, row, 3)
            if row[1] not in findings: raise Rejected('finding evidence precedes/has unknown finding key: ' + row[1])
            findings[row[1]]['evidence'].append(row[2] if kind == 'finding_evidence' else {'manifest': row[2]})
        elif kind in memo_names:
            _arity(line, row, 2); _memo_add(out['source_memo'], kind, row[1])
        else:
            raise Rejected(f'unknown review form row `{kind}` at line {line}')
    out.update(singles); out['findings'] = list(findings.values())
    return out


def _parse_side(rows):
    out = {'evidence': [], 'unknowns': [], 'coverage': {'excluded': []}, 'proposed_next_actions': []}; singles = {}
    for line, row in rows:
        kind = row[0]
        if kind in {'status', 'summary'}:
            _arity(line, row, 2); _singleton(singles, kind, row[1], line)
            if kind=='status' and row[1] and row[1] not in {'done','blocked','failed'}:
                raise Rejected(f'form line {line} status must be done, blocked, or failed')
        elif kind in {'evidence', 'evidence_manifest', 'unknown', 'excluded', 'next_action'}:
            _arity(line, row, 2)
            if kind == 'evidence': out['evidence'].append(row[1])
            elif kind == 'evidence_manifest': out['evidence'].append({'manifest': row[1]})
            elif kind == 'unknown': out['unknowns'].append(row[1])
            elif kind == 'excluded': out['coverage']['excluded'].append(row[1])
            else: out['proposed_next_actions'].append(row[1])
        elif kind == 'coverage':
            _arity(line, row, 3)
            try: values = {'examined': int(row[1]), 'total': int(row[2])}
            except ValueError as exc: raise Rejected(f'form line {line} coverage values must be integers') from exc
            if 'examined' in out['coverage']: raise Rejected('duplicate coverage form row')
            out['coverage'].update(values)
        else:
            raise Rejected(f'unknown side-result form row `{kind}` at line {line}')
    out.update(singles)
    return out


def _parse_side_request(kind,rows):
    operation=kind.removeprefix('side_request_')
    out={'kind':operation,'current_findings':[],'competing_explanations':[],'attempted':[],
         'evidence':[],'affected_commitments':[]};singles={}
    mapping={'current_finding':'current_findings','competing_explanation':'competing_explanations',
             'attempted':'attempted','affected_commitment':'affected_commitments'}
    for line,row in rows:
        name=row[0]
        if name in {'class','question','requested_output','verification_plan','benefit','decision_key'}:
            _arity(line,row,2);_singleton(singles,name,row[1],line)
        elif name in mapping:
            _arity(line,row,2);out[mapping[name]].append(row[1])
        elif name in {'evidence','evidence_manifest'}:
            _arity(line,row,2);out['evidence'].append(row[1] if name=='evidence' else {'manifest':row[1]})
        else:
            raise Rejected(f'unknown side-request form row `{name}` at line {line}')
    out.update(singles)
    return out


def _parse_planning_request(rows):
    out={'source_paths':[],'directives':[],'affected_wp_ids':[]};singles={}
    for line,row in rows:
        name=row[0]
        if name in {'reason','question','target_milestone'}:
            _arity(line,row,2);_singleton(singles,name,row[1],line)
        elif name=='source_path':
            _arity(line,row,2);out['source_paths'].append(row[1])
        elif name=='directive':
            _arity(line,row,4);out['directives'].append({'id':row[1],'intent':row[2],'raw_text':row[3]})
        elif name=='affected_wp':
            _arity(line,row,2);out['affected_wp_ids'].append(row[1])
        else:
            raise Rejected(f'unknown planning-request form row `{name}` at line {line}')
    out.update(singles)
    return out


_PROJECT_LIST_ROWS = {
    'project_boundary': 'boundaries', 'project_risk': 'strategic_risks',
    'project_hypothesis': 'working_hypotheses', 'project_question': 'open_questions',
}
_WP_CHILDREN = {
    'constraint': 'constraints', 'exit': 'exit_conditions', 'dependency': 'dependencies',
    'skill': 'required_skills', 'scope_path': ('scope', 'paths'), 'scope_ref': ('scope', 'refs'),
    'check': 'required_checks', 'commitment': 'depends_on_commitments',
}


def _new_wp(row):
    return {'id': row[1], 'owner_role': row[2], 'specialty': row[3], 'impact': row[4], 'review_policy': row[5],
            'title': row[6], 'objective': row[7], 'constraints': [], 'exit_conditions': [], 'dependencies': [],
            'required_skills': [], 'scope': {'paths': [], 'refs': []}, 'required_checks': [], 'depends_on_commitments': []}


def _wp_child(work, suffix, value):
    field = _WP_CHILDREN[suffix]
    if isinstance(field, tuple): work[field[0]][field[1]].append(value)
    else: work[field].append(value)


def _parse_planner(kind, rows):
    full = kind == 'planner_full'
    out = {'mode': 'full' if full else 'patch', 'basis_refs': [], 'invalidate_accepted': []}
    singles = {}; commitments = {}; works = {}
    if full:
        project = {'commitments': [], 'boundaries': [], 'strategic_risks': [], 'working_hypotheses': [], 'open_questions': []}
        out.update({'project': project, 'plan': {'work_packages': []}})
        commitment_prefix = 'commitment'; wp_prefix = 'wp'
    else:
        project_set = {}; upserts = []; work_upserts = []
        out.update({'project_patch': {'set': project_set, 'commitments': {'upsert': upserts, 'remove': []}},
                    'plan_patch': {'work_packages': {'upsert': work_upserts, 'remove': []}}})
        commitment_prefix = 'commitment_upsert'; wp_prefix = 'wp_upsert'
    for line, row in rows:
        name = row[0]
        if name == 'reason':
            _arity(line, row, 2); _singleton(singles, name, row[1], line)
        elif name == 'basis_path':
            _arity(line, row, 2); out['basis_refs'].append(row[1])
        elif name == 'invalidate':
            _arity(line, row, 2); out['invalidate_accepted'].append(row[1])
        elif full and name in {'project_goal', 'project_phase'}:
            _arity(line, row, 2); _singleton(project, 'goal' if name == 'project_goal' else 'phase', row[1], line)
        elif full and name in _PROJECT_LIST_ROWS:
            _arity(line, row, 2); project[_PROJECT_LIST_ROWS[name]].append(row[1])
        elif not full and name == 'project_set':
            _arity(line, row, 3)
            if row[1] not in {'goal', 'phase'}: raise Rejected(f'form line {line} invalid scalar project field: {row[1]}')
            _singleton(project_set, row[1], row[2], line)
        elif not full and name in {'project_list', 'project_clear'}:
            _arity(line, row, 3 if name == 'project_list' else 2)
            if row[1] not in {'boundaries', 'strategic_risks', 'working_hypotheses', 'open_questions'}:
                raise Rejected(f'form line {line} invalid list project field: {row[1]}')
            if name == 'project_clear':
                if row[1] in project_set: raise Rejected('project list field has both values and clear: ' + row[1])
                project_set[row[1]] = []
            else:
                if row[1] in project_set and not isinstance(project_set[row[1]], list): raise Rejected('duplicate project field form mode: ' + row[1])
                project_set.setdefault(row[1], []).append(row[2])
        elif name == commitment_prefix:
            _arity(line, row, 4)
            if row[1] in commitments: raise Rejected('duplicate commitment form ID: ' + row[1])
            item = {'id': row[1], 'scope': row[2], 'statement': row[3], 'applies_to': []}; commitments[row[1]] = item
            (project['commitments'] if full else upserts).append(item)
        elif name == commitment_prefix + '_applies':
            _arity(line, row, 3)
            if row[1] not in commitments: raise Rejected('commitment applies row precedes/has unknown ID: ' + row[1])
            commitments[row[1]]['applies_to'].append(row[2])
        elif not full and name == 'commitment_remove':
            _arity(line, row, 2); out['project_patch']['commitments']['remove'].append(row[1])
        elif name == wp_prefix:
            _arity(line, row, 8)
            if row[1] in works: raise Rejected('duplicate WP form ID: ' + row[1])
            item = _new_wp(row); works[row[1]] = item
            (out['plan']['work_packages'] if full else work_upserts).append(item)
        elif name.startswith(wp_prefix + '_') and name[len(wp_prefix) + 1:] in _WP_CHILDREN:
            _arity(line, row, 3); suffix = name[len(wp_prefix) + 1:]
            if row[1] not in works: raise Rejected('WP child row precedes/has unknown ID: ' + row[1])
            _wp_child(works[row[1]], suffix, row[2])
        elif not full and name == 'wp_remove':
            _arity(line, row, 2); out['plan_patch']['work_packages']['remove'].append(row[1])
        else:
            raise Rejected(f'unknown planner form row `{name}` at line {line}')
    out.update(singles)
    return out


def parse_form(data, *, expected_kind=None):
    kind, rows = _read(data)
    if expected_kind:
        allowed = {'planner_result': {'planner_full', 'planner_patch'},
                   'side_request': {'side_request_luna_aux','side_request_synthesis'}}.get(expected_kind, {expected_kind})
        if kind not in allowed:
            raise Rejected(f'semantic form kind {kind} does not match packet output {expected_kind}')
    if kind == 'result': return _parse_result(rows)
    if kind == 'review': return _parse_review(rows)
    if kind == 'side_result': return _parse_side(rows)
    if kind.startswith('side_request_'): return _parse_side_request(kind,rows)
    if kind == 'planning_request': return _parse_planning_request(rows)
    return _parse_planner(kind, rows)
