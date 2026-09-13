"""Semantic conformance API. The caller is a trusted coordinator, not an untrusted worker.

Orca alone starts/stops/waits for workers. These methods never infer liveness,
retry transport, cancel a process, reserve model spend or run a scheduling loop.
"""
from pathlib import Path
import copy,json
from common import ROOT, Rejected, atomic_write, digest, encode, identifier, load, logical_relative
from contracts import validate, validate_project_plan, index, contract_digest, patch_impact, materialize_planner_result
from records import Records, milestone_id, MILESTONE_ID
from routing import OWNERS, R2_TRIGGER_TAGS, validate_policy, validate_operator, dispatch_bindings, fixed_binding, route_side, next_review, admission, require_drained
from verification import evidence_path, evidence_logical_paths, head, snapshot, verify_evidence, materialize_evidence, materialize_scope_refs, write_evidence_manifest, run_checks

class Guards:
    def __init__(self,repo): self.files=Records(repo)
    def state(self): return self.files.read()
    def policy(self,s=None):
        s=s or self.state();p=self.files.get(s['policy_ref']);validate_policy(p);return p
    def operator(self):
        value=self.files.read_operator();validate_operator(value);return value
    def set_operator(self,value):
        validate_operator(value)
        with self.files.lock(): self.files.write_operator(value)
        return value
    def initialize(self,project,plan,run_id,*,policy=None,operator=None,simulation=False,bootstrap_inventory=None):
        validate_project_plan(project,plan);milestone_id(plan['plan_id']);identifier(run_id)
        p=policy or load(ROOT/'config/policy.yaml');validate_policy(p)
        op=operator or load(ROOT/'config/operator-defaults.yaml');validate_operator(op)
        for w in plan['work_packages']:
            if not set(w['required_checks']) <= set(p['checks']): raise Rejected('unknown approved check')
        with self.files.lock():
            if any((self.files.root/n).exists() for n in ['semantic.yaml','current.yaml','project.yaml','plan.yaml','state.yaml']):
                raise Rejected('existing project: explicit archived migration required')
            self.files.ensure_milestone(plan['plan_id'])
            pref=self.files.put('config','policy',p)
            inventory_ref=self.files.put('payloads','bootstrap-inventory-'+digest(bootstrap_inventory),bootstrap_inventory) if bootstrap_inventory is not None else None
            self.files.write_operator(op)
            state={'schema_version':9,'run_id':run_id,'simulation':bool(simulation),
                               'project':project,'plan':plan,'policy_ref':pref,'accepted':{},'current_candidates':{},
                               'invalidations':{},'latest_sources':{},'last_planner':None,'initial_head':head(self.files.repo), 'control_ref':None}
            if inventory_ref is not None:state['bootstrap_inventory_ref']=inventory_ref
            self.files.commit(state)
    def _wp(self,s,wid):
        w=index(s['plan']).get(wid)
        if not w: raise Rejected('unknown WP: '+str(wid))
        return w
    def _binding(self,ref): return self.files.get(ref)
    def _view(self,s,view):
        validate('runtime_view',view)
        if view['project_id']!=s['project']['project_id'] or view['run_id']!=s['run_id'] or view['simulation']!=s['simulation']:
            raise Rejected('runtime view identity/mode mismatch')
    def _identity(self,s,receipt):
        if receipt['run_id']!=s['run_id'] or receipt['simulation']!=s['simulation']:
            raise Rejected('native receipt run/simulation mismatch')
    def _control(self,s):
        if not s['control_ref']: raise Rejected('attach an actual fixed-model Control receipt before managed actions')
        c=self.files.get(s['control_ref'])
        if c['effective']!=fixed_binding(self.policy(s),'control'): raise Rejected('control binding mismatch')
        if c['role_contract_digest']!=digest((ROOT/'references/roles/control.md').read_text()):
            raise Rejected('control role contract changed; run mats activate in the current Control session')
    def attach_control(self,receipt):
        validate('control_receipt',receipt);s=self.state();self._identity(s,receipt)
        if receipt['effective']!=fixed_binding(self.policy(s),'control'): raise Rejected('current agent is not the pinned Control model/effort')
        if receipt['role_contract_digest']!=digest((ROOT/'references/roles/control.md').read_text()):
            raise Rejected('control role contract identity mismatch')
        with self.files.lock():
            # A session can legitimately survive a Skill update.  The immutable
            # receipt ID therefore identifies the complete receipt, not only the
            # stable host session, while legacy control-<session> refs stay valid.
            s=self.state();s['control_ref']=self.files.put('provenance','control-'+digest(receipt),receipt);self.files.commit(s)
        return s['control_ref']
    def attach_current_control(self,session_id):
        """Generate the root receipt from host session identity + private fixed binding."""
        if not isinstance(session_id,str) or not session_id.strip():
            raise Rejected('host does not expose CODEX_SESSION_ID for automatic Control attachment')
        s=self.state();receipt={'schema_version':9,'run_id':s['run_id'],'session_id':session_id.strip(),
            'effective':fixed_binding(self.policy(s),'control'),
            'role_contract_digest':digest((ROOT/'references/roles/control.md').read_text()),
            'source':'MATS automatic root receipt from host session identity and fixed private binding',
            'simulation':s['simulation']}
        return self.attach_control(receipt)
    def resume_anchor(self,packet_ref=None):
        """Reconstruct the current actor identity after waits, interruption or compaction."""
        s=self.state();self._control(s)
        if packet_ref is None:
            role='control';wp_id=None;specialty='task-orchestration';pref=None
            role_path=(ROOT/'references/roles/control.md').resolve()
            required=[role_path,(ROOT/'references/workflow.md').resolve(),(ROOT/'references/routing.md').resolve()]
            permitted=['process_events','dispatch_by_semantic_operation','apply_guarded_transition','wait_again']
            contract_digest_value=digest(role_path.read_text())
        else:
            packet=self.files.get(packet_ref);self._current_contract(s,packet)
            role=packet['role']
            if role not in OWNERS: raise Rejected('only Control or an Owner packet may anchor a managed wait')
            wp_id=packet['wp_id'];specialty=packet['specialty'];pref=packet_ref
            role_path=(ROOT/'references/roles'/f'{role}.md').resolve()
            required=[role_path,(self.files.root/packet_ref['path']).resolve()]
            permitted=['process_aux_events','verify_or_reject_aux_evidence','continue_same_wp','wait_again']
            contract_digest_value=packet['role_contract_digest']
        return {'schema_version':9,'authority_role':role,'specialty':specialty,'wp_id':wp_id,
                'project_id':s['project']['project_id'],'run_id':s['run_id'],'plan_version':s['plan']['version'],
                'packet_ref':pref,'role_contract_path':role_path.as_posix(),'role_contract_digest':contract_digest_value,
                'required_rereads':[p.as_posix() for p in required],'permitted_next_actions':permitted,
                'refresh_rule':'refresh before processing events; a checkpoint is not failure and never changes role, WP or authority'}
    def directive(self,value):
        validate('directive',value)
        return self.files.put('directives',value['id'],value)

    def create_planning_request_form(self):
        """Create one fixed semantic form; Control never authors request YAML."""
        s=self.state();self._control(s)
        from forms import render_planning_request_form
        path=self.files.planning_request_form_path(create=True)
        atomic_write(path,render_planning_request_form())
        return path

    def planning_request(self,value):
        """Materialize directives and internal refs from a Control semantic form."""
        s=self.state();self._control(s)
        if value.get('reason')=='bootstrap':raise Rejected('bootstrap planning request is generated only by bootstrap')
        directive_ids=[];directives=[]
        for directive in value.get('directives',[]):
            validate('directive',directive);directives.append(copy.deepcopy(directive));directive_ids.append(directive['id'])
        refs=[self._materialize_internal_ref(path) for path in value.get('source_paths',[])]
        for ref in refs:self._source(ref)
        request={'reason':value.get('reason'),'question':value.get('question'),'source_refs':refs,
                 'directive_ids':directive_ids,'affected_wp_ids':value.get('affected_wp_ids',[])}
        if value.get('target_milestone'):request['target_milestone_id']=value['target_milestone']
        validate('planning_request',request)
        for directive in directives:
            old=self.files.named('directives',directive['id'])
            if old is not None and self.files.get(old)!=directive:
                raise Rejected('immutable directive ID already has different content: '+directive['id'])
        with self.files.lock():
            for directive in directives:self.directive(directive)
            return self.files.put('requests','planning-'+digest(request),request)

    def planning_request_from_conflict(self,source_ref):
        """Preserve an Owner/Reviewer conflict verbatim; Control adds no design."""
        source=self._source(source_ref);memo=source.get('result',{}).get('source_memo',{})
        question=memo.get('decision_requested') if isinstance(memo,dict) else None
        if not isinstance(question,str) or not question.strip():
            raise Rejected('plan conflict source lacks a decision request',code='PLAN_CONFLICT_SOURCE_INCOMPLETE')
        wp_id=source.get('wp_id')
        if not isinstance(wp_id,str):raise Rejected('plan conflict source lacks a WP identity',code='PLAN_CONFLICT_SOURCE_INCOMPLETE')
        request={'reason':'plan_conflict','question':question,'source_refs':[source_ref],
                 'directive_ids':[],'affected_wp_ids':[wp_id]}
        validate('planning_request',request)
        return self.files.put('requests','planning-'+digest(request),request)
    def _internal_memo_source(self,value):
        if not isinstance(value,str) or not value.strip():return None
        try:path=self.files.control_path(value,prefixes=('results','reviews'))
        except Rejected:return None
        if not path.is_file():return None
        ref={'path':logical_relative(self.files.root,path),'sha256':digest(load(path))}
        self.files.get(ref);return ref
    def _delivery_evidence(self,result):
        items=list(result.get('evidence',[])) if isinstance(result,dict) else []
        memo=result.get('source_memo') if isinstance(result,dict) else None
        if isinstance(memo,dict):items += [item for item in memo.get('evidence_refs',[]) if self._internal_memo_source(item) is None]
        for side in result.get('consumed_sides',[]) if isinstance(result,dict) else []:
            if isinstance(side,dict):items += list(side.get('verified_evidence',[]))
        for spec in result.get('recovered_specs',[]) if isinstance(result,dict) else []:
            if isinstance(spec,dict):
                if spec.get('subject') is not None:items.append(spec['subject'])
                items += list(spec.get('evidence',[]))
        return items
    @staticmethod
    def _role_result_contract(role,result):
        if role!='research' and isinstance(result,dict) and 'recovered_specs' in result:
            raise Rejected('recovered_specs may be authored only by a Research Owner')
    def _packet_snapshot(self,s,packet,w,repo,declared):
        roots=self.policy(s)['evidence_roots'];declared=list(declared)
        declared_paths=evidence_logical_paths(repo,declared,roots)
        return snapshot(repo,packet['base_commit'],w['scope']['paths'],declared_read_paths=declared_paths)
    def dependencies(self,s,w):
        out={}
        for wid in w['dependencies']:
            a=s['accepted'].get(wid)
            if not a: raise Rejected('dependency is not semantically accepted: '+wid)
            c=self.files.get(a['candidate_ref']);cw=self._wp(s,wid)
            if c['contract_digest']!=contract_digest(s['project'],cw): raise Rejected('stale dependency acceptance')
            out[wid]=a['candidate_ref']
        return out
    def _current_contract(self,s,packet):
        if packet['policy_digest']!=s['policy_ref']['sha256']: raise Rejected('policy changed in-flight')
        if packet['wp_id'] is not None:
            w=self._wp(s,packet['wp_id'])
            if packet['contract_digest']!=contract_digest(s['project'],w): raise Rejected('affected WP contract changed')
            if packet['dependency_bindings']!=self.dependencies(s,w): raise Rejected('upstream accepted content changed')
            # Explicit invalidation also fences an unchanged downstream contract.
            if packet['plan_version'] <= s['invalidations'].get(w['id'],0): raise Rejected('WP was explicitly invalidated after packet creation')
    def _source(self,ref):
        v=self.files.get(ref)
        if v.get('kind') not in {'owner_result','review','side_request','side_result'}: raise Rejected('not a source-authored semantic artifact')
        return v
    @staticmethod
    def _planning_occasion(request):
        out={k:copy.deepcopy(request[k]) for k in ('reason','question','source_refs','directive_ids','affected_wp_ids')}
        if 'target_milestone_id' in request:out['target_milestone_id']=request['target_milestone_id']
        return out
    def _record_planner_rejection(self,binding_ref,packet,result,stage,detail,*,proposal_ref=None):
        rejected_result_ref=self.files.put('planner_rejected_payloads',digest(result),result)
        rec={'schema_version':9,'kind':'planner_rejection','stage':stage,'packet_ref':self._binding(binding_ref)['packet_ref'],
             'binding_ref':binding_ref,'request':copy.deepcopy(packet['request']),'base_plan_version':packet['plan_version'],
             'result_digest':digest(result),'rejected_result_ref':rejected_result_ref,'detail':str(detail),
             'repairable':self.state()['plan']['version']==packet['plan_version']}
        if proposal_ref is not None: rec['proposal_ref']=proposal_ref
        validate('planner_rejection',rec)
        return self.files.put('planner_rejections',digest({'packet':rec['packet_ref'],'result':rec['result_digest'],'stage':stage,'detail':rec['detail']}),rec)
    def _planner_semantic_preview(self,s,b,packet,result):
        validate('planner_result',result)
        if result['base_plan_version']!=packet['plan_version']:
            raise Rejected('proposal base does not match Planner packet')
        reason=packet['request']['reason']
        if reason=='bootstrap' and result['mode']!='full':
            raise Rejected('bootstrap Planner must return a complete project + plan')
        if reason!='bootstrap' and result['mode']!='patch':
            raise Rejected('runtime Planner decisions must return a sparse patch, not restate the whole project')
        for ref in result['basis_refs']: self.files.get(ref)
        new_project,new_plan=materialize_planner_result(s['project'],s['plan'],result)
        target=packet['request'].get('target_milestone_id')
        if target:
            new_plan['plan_id']=target;validate_project_plan(new_project,new_plan)
        elif new_plan['plan_id']!=s['plan']['plan_id']:
            raise Rejected('plan_id changes only through request-pinned target_milestone_id')
        affected=patch_impact(s['project'],s['plan'],new_project,new_plan)
        invalid=set(result['invalidate_accepted'])
        if not invalid <= set(index(s['plan'])) or not (affected & set(s['accepted'])) <= invalid:
            raise Rejected('affected accepted closure must be explicitly invalidated')
        from contracts import closure
        affected |= closure(invalid,s['plan'],new_plan)
        if not (affected & set(s['accepted'])) <= invalid:
            raise Rejected('invalidation must include accepted descendants')
        for w in new_plan['work_packages']:
            if not set(w['required_checks']) <= set(self.policy(s)['checks']):
                raise Rejected('unapproved check in plan')
        return new_project,new_plan,affected

    def _materialize_memo(self,repo,memo,roots,workspace_snapshot):
        if not isinstance(memo,dict): raise Rejected('source_memo must be an object')
        out=copy.deepcopy(memo)
        for key,default in (('observations',[]),('downstream_impact',[]),('decision_requested',''),('evidence_refs',[])):
            out.setdefault(key,copy.deepcopy(default))
        domain=[];sources=list(out.get('source_refs',[]))
        for item in out['evidence_refs']:
            source=self._internal_memo_source(item)
            if source is None:domain.append(item)
            else:sources.append(source)
        out['evidence_refs']=materialize_evidence(repo,domain,roots,workspace_snapshot)
        out['source_refs']=[self._materialize_internal_ref(ref,prefixes=('results','reviews')) for ref in sources]
        return out

    def _materialize_internal_ref(self,value,*,prefixes=()):
        """Turn a model-facing .task path into an immutable internal reference."""
        if isinstance(value,dict):
            if prefixes:self.files.control_path(value.get('path'),prefixes=prefixes)
            self.files.get(value)
            return copy.deepcopy(value)
        if not isinstance(value,str) or not value.strip():
            raise Rejected('artifact reference must be a non-empty .task path')
        path=self.files.control_path(value,prefixes=prefixes)
        if not path.is_file():raise Rejected('artifact reference path does not exist: '+value)
        ref={'path':logical_relative(self.files.root,path),'sha256':digest(load(path))}
        self.files.get(ref)
        return ref

    def prepare_delivery(self,packet_ref,result,*,workspace=None):
        """Materialize transaction-only child fields without changing semantic state."""
        s=self.state();packet=self.files.get(packet_ref);self._current_contract(s,packet)
        role=packet['role'];out=copy.deepcopy(result);out['schema_version']=9
        bindings=[b for _,b in self.files.all('bindings') if b['packet_ref']==packet_ref and b['role']==role]
        if not bindings: raise Rejected('delivery preparation requires a bound packet')
        repo=None;live=None
        if role!='planner':
            if workspace is None: raise Rejected('delivery preparation requires the assigned --workspace')
            wanted=Path(workspace).resolve()
            matches=[b for b in bindings if Path(b['receipt']['workspace_path']).resolve()==wanted]
            # One immutable packet may have multiple native-failed retry bindings to
            # the same workspace. Transaction materialization depends on packet +
            # workspace content, not on which equivalent attempt reached delivery.
            if not matches: raise Rejected('assigned workspace does not match a packet binding')
            repo=wanted;w=self._wp(s,packet['wp_id'])
        roots=self.policy(s)['evidence_roots']
        if role in OWNERS:
            self._role_result_contract(role,out)
            live=self._packet_snapshot(s,packet,w,repo,self._delivery_evidence(out))
            # Snapshot is Guard-owned. Always replace stale/model-authored values so
            # absence of a private snapshot API can never become a worker blocker.
            out['snapshot']=live['sha256']
            out['evidence']=materialize_evidence(repo,out.get('evidence',[]),roots,live['sha256'])
            out['source_memo']=self._materialize_memo(repo,out.get('source_memo'),roots,live['sha256'])
            for spec in out.get('recovered_specs',[]):
                if isinstance(spec.get('subject'),dict) and set(spec['subject'])=={'manifest'}:
                    raise Rejected('recovered spec subject must name one binary file, not an evidence manifest')
                spec['subject']=materialize_evidence(repo,[spec.get('subject')],roots,live['sha256'])[0]
                spec['evidence']=materialize_evidence(repo,spec.get('evidence',[]),roots,live['sha256'])
            out.setdefault('consumed_sides',[])
            for item in out['consumed_sides']:
                if isinstance(item,dict):
                    if 'side_ref' in item:item['side_ref']=self._materialize_internal_ref(item['side_ref'],prefixes=('results',))
                if isinstance(item,dict) and 'verified_evidence' in item:
                    item['verified_evidence']=materialize_evidence(repo,item['verified_evidence'],roots,live['sha256'])
        elif role.startswith('review_'):
            live=self.verify_candidate(self.files.get(packet['candidate_ref']),s,repo_override=repo)
            out['target_digest']=packet['candidate_ref']['sha256']
            out['source_memo']=self._materialize_memo(repo,out.get('source_memo'),roots,live['sha256'])
            for finding in out.get('findings',[]):
                if isinstance(finding,dict):finding['evidence']=materialize_evidence(repo,finding.get('evidence',[]),roots,live['sha256'])
        elif role in {'luna_aux','synthesis'}:
            source=self.files.get(packet['request'])
            live=self._packet_snapshot(s,packet,w,repo,
                                       list(source['request']['evidence'])+list(out.get('evidence',[])))
            out['evidence']=materialize_evidence(repo,out.get('evidence',[]),roots,live['sha256'])
            if isinstance(out.get('coverage'),dict):out['coverage'].setdefault('excluded',[])
        elif role=='planner':
            expected_mode='full' if packet['request'].get('reason')=='bootstrap' else 'patch'
            out['mode']=expected_mode
            if expected_mode=='full':
                out.pop('project_patch',None);out.pop('plan_patch',None)
            else:
                out.pop('project',None);out.pop('plan',None)
            out['base_plan_version']=packet['plan_version'];out.setdefault('basis_refs',[]);out.setdefault('invalidate_accepted',[])
            out['basis_refs']=[self._materialize_internal_ref(ref) for ref in out['basis_refs']]
            old={w['id']:w for w in s['plan']['work_packages']}
            plan_value=out.get('plan');patch_value=out.get('plan_patch')
            if out.get('mode')=='full':targets=plan_value.get('work_packages',[]) if isinstance(plan_value,dict) else []
            else:
                packages=patch_value.get('work_packages') if isinstance(patch_value,dict) else None
                targets=packages.get('upsert',[]) if isinstance(packages,dict) else []
            def draft_refs(work):
                scope=work.get('scope') if isinstance(work,dict) else None
                return scope.get('refs',[]) if isinstance(scope,dict) and isinstance(scope.get('refs',[]),list) else []
            needs_workspace=any(any(not isinstance(ref,dict) or set(ref)!={'path','sha256','version'} for ref in draft_refs(w)) for w in targets)
            planner_repo=None
            if workspace is not None:
                wanted=Path(workspace).resolve()
                if not any(Path(b['receipt']['workspace_path']).resolve()==wanted for b in bindings):
                    raise Rejected('assigned workspace does not match a Planner packet binding')
                planner_repo=wanted
            elif needs_workspace:
                raise Rejected('new scope.refs paths require the injected --workspace finalizer argument')
            for work in targets:
                if not isinstance(work,dict) or not isinstance(work.get('scope'),dict) or 'refs' not in work['scope']:
                    continue
                prior=(old.get(work.get('id')) or {}).get('scope',{}).get('refs',[])
                work['scope']['refs']=materialize_scope_refs(planner_repo,work['scope']['refs'],roots,prior)
            if out.get('mode')=='full':
                if isinstance(out.get('project'),dict):
                    out['project']['schema_version']=9;out['project']['project_id']=s['project']['project_id']
                if isinstance(out.get('plan'),dict):
                    target=packet['request'].get('target_milestone_id') or s['plan']['plan_id']
                    out['plan']['schema_version']=9;out['plan']['project_id']=s['project']['project_id']
                    out['plan']['plan_id']=target;out['plan']['version']=s['plan']['version']+1
        return out

    def create_evidence_manifest(self,packet_ref,output,inputs,*,workspace):
        """Owner-only bounded manifest generation in its declared write scope/evidence roots."""
        s=self.state();packet=self.files.get(packet_ref);self._current_contract(s,packet)
        if packet['role'] not in OWNERS: raise Rejected('only an Owner may create a domain evidence manifest')
        repo=Path(workspace).resolve();bindings=[b for _,b in self.files.all('bindings') if b['packet_ref']==packet_ref and Path(b['receipt']['workspace_path']).resolve()==repo]
        if not bindings: raise Rejected('assigned workspace does not match a packet binding')
        roots=self.policy(s)['evidence_roots'];target=evidence_path(repo,output,roots);w=self._wp(s,packet['wp_id'])
        try:
            rel=target.relative_to(repo).as_posix()
        except ValueError:
            rel=None
        if rel is not None and not any(rel==p or rel.startswith(p+'/') for p in w['scope']['paths']):
            raise Rejected('evidence manifest output is outside Owner write scope')
        _,count=write_evidence_manifest(repo,output,inputs,roots)
        # Snapshot is intentionally calculated after the manifest write. The manifest
        # does not embed the snapshot, avoiding a self-referential digest.
        live=self._packet_snapshot(s,packet,w,repo,[{'manifest':output}])
        return {'evidence':[{'manifest':output}],'entry_count':count,'candidate_snapshot':live['sha256']}

    def check_delivery(self,packet_ref,result):
        """Read-only, packet-bound mechanical checks a child runs before delivery."""
        s=self.state();packet=self.files.get(packet_ref);self._current_contract(s,packet)
        kinds={'research':'result','engineering':'result','luna_aux':'side_result','synthesis':'side_result',
               'planner':'planner_result','review_r1':'review','review_r2':'review'}
        kind=kinds.get(packet.get('role'))
        if kind is None or packet.get('output_contract')!=kind:
            raise Rejected('packet role/output contract mismatch')
        validate(kind,result)
        if packet['role'] in OWNERS:self._role_result_contract(packet['role'],result)
        memo=result.get('source_memo') if isinstance(result,dict) else None
        if isinstance(memo,dict):
            for ref in memo.get('source_refs',[]):self.files.get(ref)
        bindings=[(ref,b) for ref,b in self.files.all('bindings') if b['packet_ref']==packet_ref and b['role']==packet['role']]
        if not bindings: raise Rejected('delivery check requires a bound packet')
        out={'valid':True,'kind':kind,'packet_sha256':packet_ref['sha256'],'context_preview':True}
        if packet['role']=='planner':
            _,new_plan,affected=self._planner_semantic_preview(s,None,packet,result)
            out.update({'target_plan_version':new_plan['version'],'affected_closure':sorted(affected)})
        elif packet['role'] in OWNERS:
            w=self._wp(s,packet['wp_id']);matched=None
            for bref,b in bindings:
                repo=Path(b['receipt']['workspace_path'])
                live=self._packet_snapshot(s,packet,w,repo,self._delivery_evidence(result))
                if live['sha256']==result['snapshot']:
                    matched=(bref,repo);break
            if matched is None: raise Rejected('owner delivery snapshot does not match any bound workspace')
            bref,repo=matched
            verify_evidence(repo,self._delivery_evidence(result),self.policy(s)['evidence_roots'],workspace_snapshot=result['snapshot'])
            if result['status']=='candidate':
                self._validate_consumption({'binding_ref':bref,'wp_id':packet['wp_id'],'result':result},s)
        elif packet['role'].startswith('review_'):
            if result['target_digest']!=packet['candidate_ref']['sha256']:
                raise Rejected('review delivery targets a stale/different candidate')
            candidate=self.files.get(packet['candidate_ref']);matched=None
            for _,b in bindings:
                try:
                    live=self.verify_candidate(candidate,s,repo_override=Path(b['receipt']['workspace_path']))
                    if live['sha256']==candidate['result']['snapshot']:
                        matched=b;break
                except Rejected:
                    continue
            if matched is None:
                raise Rejected('reviewer delivery workspace is not the exact candidate snapshot')
            repo=Path(matched['receipt']['workspace_path'])
            for finding in result['findings']: verify_evidence(repo,finding['evidence'],self.policy(s)['evidence_roots'],workspace_snapshot=candidate['result']['snapshot'])
            verify_evidence(repo,result['source_memo']['evidence_refs'],self.policy(s)['evidence_roots'],workspace_snapshot=candidate['result']['snapshot'])
            if packet['role']=='review_r2' and result['outcome'] in {'needs_synthesis','escalate_r2'}:
                raise Rejected('R2 cannot open another review/synthesis loop')
            if packet['role']=='review_r1' and result['outcome']=='needs_synthesis':
                requests=[ref for bref,_binding in bindings for ref in self.side_requests_for_binding(bref)
                          if self.files.get(ref)['request']['kind']=='synthesis']
                if len(requests)!=1:raise Rejected('R1 needs_synthesis requires exactly one generated Synthesis request before delivery')
                out['source_side_request_ref']=requests[0]
            if result['outcome']=='plan_conflict' and not result['source_memo']['decision_requested'].strip():
                raise Rejected('reviewer conflict requires reviewer-owned memo')
        else:
            source=self.files.get(packet['request']);matched=False
            for _,b in bindings:
                try:
                    repo=Path(b['receipt']['workspace_path'])
                    live=self._packet_snapshot(s,packet,self._wp(s,packet['wp_id']),repo,
                                               list(source['request']['evidence'])+list(result['evidence']))
                    verify_evidence(repo,source['request']['evidence']+result['evidence'],self.policy(s)['evidence_roots'],workspace_snapshot=live['sha256'])
                    matched=True;break
                except Rejected:
                    continue
            if not matched: raise Rejected('side delivery evidence does not match any bound workspace')
            if packet['role']=='luna_aux' and result['coverage']['total']==0:
                raise Rejected('auxiliary must state nonzero coverage denominator')
        return out
    def prepare_side_request(self,binding_ref,request):
        b=self._binding(binding_ref);s=self.state();packet=self.files.get(b['packet_ref']);self._current_contract(s,packet)
        out=copy.deepcopy(request);out.setdefault('schema_version',9);out.setdefault('affected_commitments',[])
        if 'evidence' not in out and b['role'].startswith('review_'):
            out['evidence']=copy.deepcopy(self.files.get(packet['candidate_ref'])['result']['evidence'])
        repo=Path(b['receipt']['workspace_path']);items=out.get('evidence',[])
        if any(not (isinstance(item,dict) and set(item)=={'path','sha256','version'}) for item in items):
            anchor_ref=b['packet_ref'];anchor_packet=packet
            if b['role'].startswith('review_'):
                candidate=self.files.get(packet['candidate_ref']);owner=self._binding(candidate['binding_ref'])
                anchor_ref=owner['packet_ref'];anchor_packet=self.files.get(anchor_ref)
            w=self._wp(s,packet['wp_id']);live=self._packet_snapshot(s,anchor_packet,w,repo,items)
            out['evidence']=materialize_evidence(repo,items,self.policy(s)['evidence_roots'],live['sha256'])
            return out,live['sha256']
        return out,None

    def create_side_request_form(self,binding_ref,operation,*,caller_session):
        """Create the sole model-editable form for one Owner/R1 side request."""
        if operation not in {'luna_aux','synthesis'}:raise Rejected('side request operation must be luna_aux or synthesis')
        b=self._binding(binding_ref);s=self.state();packet=self.files.get(b['packet_ref']);self._current_contract(s,packet)
        if b['role'] not in OWNERS|{'review_r1'} or caller_session!=b['receipt']['session_id']:
            raise Rejected('side request form must come from the attested Owner or R1 source')
        if b['role']=='review_r1' and operation!='synthesis':
            raise Rejected('R1 may request Synthesis only; Luna Aux is Owner advice')
        from forms import render_side_request_form
        path=self.files.side_request_form_path(b['receipt']['dispatch_id'],operation,create=True)
        atomic_write(path,render_side_request_form(operation))
        return path

    def side_request(self,binding_ref,request,*,caller_session):
        request,workspace_snapshot=self.prepare_side_request(binding_ref,request);validate('side_request',request);route_side(request)
        b=self._binding(binding_ref);s=self.state();packet=self.files.get(b['packet_ref'])
        if b['role'] not in OWNERS|{'review_r1'} or caller_session!=b['receipt']['session_id']:
            raise Rejected('side request must come from the attested owner or R1 source, not Control')
        if b['role']=='review_r1' and request['kind']!='synthesis':
            raise Rejected('R1 may request Synthesis only; Luna Aux is Owner advice')
        verify_evidence(Path(b['receipt']['workspace_path']),request['evidence'],self.policy(s)['evidence_roots'],workspace_snapshot=workspace_snapshot)
        v={'kind':'side_request','binding_ref':binding_ref,'wp_id':packet['wp_id'], 'contract_digest':packet['contract_digest'], 'request':request}
        return self.files.put('requests',digest(v),v)

    def side_requests_for_binding(self,binding_ref):
        """Project source-created requests without transcript or directory discovery."""
        return [ref for ref,value in self.files.all('requests')
                if value.get('kind')=='side_request' and value.get('binding_ref')==binding_ref]
    def issue(self,name,operation,*,wp_id=None,request=None,cyber=False):
        from packets import build
        if type(cyber) is not bool: raise Rejected('cyber classification must be boolean')
        identifier(name);s=self.state();self._control(s);p=self.policy(s)
        w=self._wp(s,wp_id) if wp_id else None
        request={} if request is None else request
        role=operation
        if operation=='owner':
            if not w or request: raise Rejected('owner uses the declared WP, not an override prompt')
            role=w['owner_role'];self.dependencies(s,w)
            latest=s['latest_sources'].get(wp_id)
            if latest and self.files.get(latest)['result']['status']=='plan_conflict':
                raise Rejected('owner conflict requires a Planner decision before continuation')
            current=s['current_candidates'].get(wp_id)
            if current and any(self.review_record(current,r) and self.review_record(current,r)['result']['outcome']=='plan_conflict' for r in ('review_r1','review_r2')):
                raise Rejected('reviewer conflict routes directly to Planner')
            if wp_id in s['accepted']: raise Rejected('accepted WP cannot be rerun without explicit invalidation')
            previous=[v for _,v in self.files.all('results') if v.get('kind')=='owner_result' and v['wp_id']==wp_id and v['contract_digest']==contract_digest(s['project'],w)]
            owner_cap=self.operator()['caps'].get('max_owner_candidates_per_wp')
            if owner_cap is not None and len(previous)>=owner_cap:
                raise Rejected('operator owner-candidate cap reached; pause/report instead of model downgrade or semantic reinterpretation')
        elif operation in {'luna_aux','synthesis'}:
            source=self._source(request)
            if not w or source['kind']!='side_request' or source['wp_id']!=wp_id or source['contract_digest']!=contract_digest(s['project'],w):
                raise Rejected('side operation requires a matching source request')
            self._current_contract(s,self.files.get(self._binding(source['binding_ref'])['packet_ref']))
            role=route_side(source['request'])
            if role!=operation: raise Rejected('fixed side role mismatch')
            fingerprint=digest({'wp':wp_id,'contract':source['contract_digest'],'decision':source['request']['decision_key'],
                                'class':source['request']['class'],'evidence':sorted(set(e['sha256'] for e in source['request']['evidence']))})
            for _,b in self.files.all('bindings'):
                old=self.files.get(b['packet_ref'])
                if role=='synthesis' and old.get('synthesis_fingerprint')==fingerprint:
                    raise Rejected('same semantic decision/evidence already dispatched; reuse its result or bring new evidence')
        elif operation in {'review_r1','review_r2'}:
            if not w or request: raise Rejected('reviews derive only from the exact candidate')
            cref=s['current_candidates'].get(wp_id)
            if not cref: raise Rejected('no candidate')
            c=self.files.get(cref);self.verify_candidate(c,s)
            r0ref=self.files.named('r0',cref['sha256'])
            if not r0ref or not self.files.get(r0ref)['passed']: raise Rejected('passing R0 required before review')
            if self.files.named('reviews',cref['sha256']+'-'+role): raise Rejected('review shopping forbidden for the same candidate')
            if role=='review_r2':
                r1=self.review_record(cref,'review_r1')
                if not r1 or r1['result']['outcome'] not in {'pass','escalate_r2'} or not self.needs_r2(c,s,r1):
                    raise Rejected('R2 requires eligible R1 and an explicit structural/risk trigger')
            for _,b in self.files.all('bindings'):
                old=self.files.get(b['packet_ref'])
                if b['role']==role and old.get('candidate_ref')==cref:
                    # Failed native transport may be retried through the SAME unreviewed packet.
                    raise Rejected('review already issued: reuse that packet only after native failure reconciliation')
        elif operation=='planner':
            validate('planning_request',request)
            target=request.get('target_milestone_id')
            if target:
                milestone_id(target)
                if request['reason'] not in {'project_steer','phase_gate','milestone_audit'}:
                    raise Rejected('target_milestone_id requires a project steer, phase gate or milestone audit')
                if set(s['current_candidates'])-set(s['accepted']):
                    raise Rejected('milestone transition requires every current candidate accepted or cleared')
                current=s['plan']['plan_id'];old=MILESTONE_ID.fullmatch(current);new=MILESTONE_ID.fullmatch(target)
                if old and int(new.group(1))!=int(old.group(1))+1:
                    raise Rejected('target milestone number must advance exactly once')
            repair_ref=request.get('repair_of')
            rejection=None
            if repair_ref is not None:
                rejection=self.files.get(repair_ref);validate('planner_rejection',rejection)
                if not rejection['repairable'] or rejection['base_plan_version']!=s['plan']['version']:
                    raise Rejected('Planner repair feedback is stale/non-repairable; do not retry against a changed plan')
                if self._planning_occasion(request)!=self._planning_occasion(rejection['request']):
                    raise Rejected('Planner repair must preserve the exact original planning occasion; do not broaden question/sources/directives/WP scope')
                if any(self.files.get(ref)['role']=='planner' and self.files.get(ref).get('request',{}).get('repair_of')==repair_ref for ref,_ in self.files.all('packets')):
                    raise Rejected('this Planner rejection already has a repair packet; reconcile/reuse it instead of spawning another repair')
            if request['reason']=='bootstrap':
                if request['affected_wp_ids']:
                    raise Rejected('bootstrap plans the project as a whole; affected_wp_ids must be empty')
                domain_bindings=[b for _,b in self.files.all('bindings') if b['role']!='planner']
                domain_results=[v for _,v in self.files.all('results') if v.get('role')!='planner']
                if s['last_planner'] is not None or s['accepted'] or s['current_candidates'] or domain_bindings or domain_results:
                    raise Rejected('bootstrap is only before domain execution and before any applied Planner decision; never archive/reset .task to bypass this guard')
                prior_planner=[b for _,b in self.files.all('bindings') if b['role']=='planner']
                if prior_planner and repair_ref is None:
                    raise Rejected('a prior bootstrap Planner attempt exists; retry only as an exact repair_of a Guard rejection, never by reinitializing .task')
                if repair_ref is not None and rejection['request']['reason']!='bootstrap':
                    raise Rejected('bootstrap repair_of must reference a rejected bootstrap proposal')
            for wid in request['affected_wp_ids']: self._wp(s,wid)
            ds={v['id']:v for _,v in self.files.all('directives')}
            if not set(request['directive_ids']) <= set(ds): raise Rejected('unknown raw directive')
            sources=[self._source(r) for r in request['source_refs']]
            if request['reason']=='project_steer' and not any(ds[i]['intent']=='project_steer' for i in request['directive_ids']):
                raise Rejected('project steer needs an explicit raw project directive; unknown intent is not automatic Planner work')
            if request['reason']=='plan_conflict' and not any(v.get('result',{}).get('status')=='plan_conflict' or v.get('result',{}).get('outcome')=='plan_conflict' for v in sources):
                raise Rejected('Planner conflict must carry owner OR reviewer original conflict evidence')
            if request['reason'] in {'strategic_stall','phase_gate','milestone_audit'} and not sources:
                raise Rejected('planning occasion requires source evidence, not a difficulty label')
        else: raise Rejected('unknown operation; direct role/model override forbidden')
        capkey={'luna_aux':'max_luna_aux_calls_per_wp','synthesis':'max_synthesis_calls_per_wp','planner':'max_planner_calls_per_project'}.get(role)
        cap=self.operator()['caps'].get(capkey) if capkey else None
        if cap is not None:
            n=sum(b['role']==role and (role=='planner' or self.files.get(b['packet_ref'])['wp_id']==wp_id) for _,b in self.files.all('bindings'))
            if n>=cap: raise Rejected('operator cap reached; pause/report instead of model downgrade or semantic reinterpretation')
        body=build(self,s,name,role,w,request,cyber=cyber)
        if operation=='synthesis': body['synthesis_fingerprint']=fingerprint
        return self.files.put('packets',name,body)
    def preflight(self,packet_ref,view,workspace_key,access,*,reuse_session=None,require_failed_retry=False):
        s=self.state();self._control(s);self._view(s,view)
        packet=self.files.get(packet_ref);self._current_contract(s,packet)
        if packet['role'].startswith('review_') and self.review_record(packet['candidate_ref'],packet['role']):
            raise Rejected('review already exists; do not retry until a substantive owner revision')
        prior=[b for _,b in self.files.all('bindings') if b['packet_ref']==packet_ref]
        failed={d['dispatch_id'] for d in view.get('settled_dispatches',[]) if d['outcome']=='failed'}
        if require_failed_retry and not prior:
            raise Rejected('packet retry requires a prior bound dispatch',code='PACKET_RETRY_UNBOUND')
        if any(b['receipt']['dispatch_id'] not in failed for b in prior):
            raise Rejected('reusing a dispatch packet requires native-confirmed failed attempts; inspect unknown/successful delivery first',code='PACKET_RETRY_NOT_CONFIRMED_FAILED')
        return admission(view,s['project']['project_id'],s['run_id'],packet['role'],packet['wp_id'],workspace_key,access,
                         reuse_session=reuse_session,max_parallel=self.operator()['caps']['max_parallel_operations'])
    def bind(self,packet_ref,receipt):
        validate('launch_receipt',receipt);s=self.state();self._identity(s,receipt)
        packet=self.files.get(packet_ref);self._current_contract(s,packet);role=packet['role']
        existing=self.files.named('bindings',receipt['dispatch_id'])
        if existing:
            old=self.files.get(existing)
            if old.get('role')==role and old.get('packet_ref')==packet_ref and old.get('receipt')==receipt:return existing
            raise Rejected('immutable dispatch provenance collision')
        prior_attempt=any(other['packet_ref']==packet_ref for _ref,other in self.files.all('bindings'))
        if prior_attempt:mode='native_retry';reason='PACKET_RETRY'
        elif role in OWNERS and not receipt['fresh_context']:mode='owner_continuation';reason='OWNER_CONTINUATION'
        elif role=='review_r1':mode='fresh';reason='R1_REQUIRED'
        elif role=='review_r2':mode='fresh';reason='R2_REQUIRED'
        elif role in {'luna_aux','synthesis'}:mode='fresh';reason=role.upper()+'_REQUIRED'
        elif role=='planner':
            mode='repair' if packet['request'].get('repair_of') else 'fresh';reason='PLANNER_'+packet['request']['reason'].upper()
        else:mode='fresh';reason='OWNER_REQUIRED'
        source_refs=[]
        for value in (packet.get('candidate_ref'),packet.get('request'),packet.get('request',{}).get('repair_of') if isinstance(packet.get('request'),dict) else None):
            if isinstance(value,dict) and set(value)=={'path','sha256'} and value not in source_refs:source_refs.append(value)
        if role=='planner':
            for ref in packet['request'].get('source_refs',[]):
                if ref not in source_refs:source_refs.append(ref)
        attribution={'reason_code':reason,'operation':'owner' if role in OWNERS else role,'mode':mode,
                     'source_refs':source_refs,'rework':mode in {'native_retry','owner_continuation','repair'},
                     'provider_usage':'unknown'}
        value={'role':role,'packet_ref':packet_ref,'receipt':receipt,'attribution':attribution}
        binding_plan=dispatch_bindings(self.policy(s),role,cyber=packet.get('cyber',False))
        fallback_attested=receipt.get('model_fallback')=={'used':True,'reason':'primary_model_unavailable'}
        primary_ok=receipt['effective']==binding_plan['primary'] and not receipt.get('model_fallback')
        fallback_ok=binding_plan['fallback'] is not None and receipt['effective']==binding_plan['fallback'] and fallback_attested
        if (not primary_ok and not fallback_ok) or receipt['packet_digest']!=packet_ref['sha256']:
            raise Rejected('effective model/effort, fallback attestation, or packet identity mismatch')
        if role not in OWNERS and (receipt['access']=='write' or not receipt['fresh_context']):
            raise Rejected('review/side/Planner requires read-only fresh context')
        if role.startswith('review_'):
            c=self.files.get(packet['candidate_ref'])
            observed=self.verify_candidate(c,s,repo_override=Path(receipt['workspace_path']))
            if observed['sha256']!=c['result']['snapshot']:
                raise Rejected('reviewer workspace is not the exact candidate snapshot; do not review a pristine/stale worktree')
        if role in {'luna_aux','synthesis'}:
            source=self.files.get(packet['request'])
            verify_evidence(Path(receipt['workspace_path']),source['request']['evidence'],self.policy(s)['evidence_roots'])
        if role in OWNERS and receipt['access']!='write' and self._wp(s,packet['wp_id'])['scope']['paths']:
            raise Rejected('owner with declared writes requires a writer placement')
        for _,other in self.files.all('bindings'):
            if other['receipt']['session_id']==receipt['session_id']:
                old=self.files.get(other['packet_ref'])
                if role not in OWNERS or other['role']!=role or old['wp_id']!=packet['wp_id']:
                    raise Rejected('self-review/context contamination; only same-owner same-WP continuation may reuse a session')
        return self.files.put('bindings',receipt['dispatch_id'],value)
    def _completion(self,b,receipt):
        validate('completion_receipt',receipt);s=self.state();self._identity(s,receipt)
        for k in ('run_id','task_id','dispatch_id','session_id'):
            if receipt[k]!=b['receipt'][k]: raise Rejected('native worker_done identity mismatch')

    def _worker_done_record(self,message,delivery_id,batch_dispatches,batch_has_other_events):
        if not isinstance(message,dict) or message.get('type')!='worker_done':
            raise Rejected('expected one native worker_done event')
        if message.get('delivery_contract')!='current_delivery':
            raise Rejected('worker_done event lacks the current delivery contract')
        try:payload=json.loads(message['payload'])
        except (KeyError,TypeError,json.JSONDecodeError) as exc:
            raise Rejected('worker_done payload is not one JSON object') from exc
        if not isinstance(payload,dict):raise Rejected('worker_done payload is not one JSON object')
        dispatch_id=payload.get('dispatchId');task_id=payload.get('taskId');outcome=payload.get('outcome')
        if not isinstance(dispatch_id,str):raise Rejected('worker_done payload lacks dispatchId')
        binding_ref=self.files.named('bindings',dispatch_id)
        if binding_ref is None:raise Rejected('worker_done references an unknown managed dispatch')
        b=self._binding(binding_ref);native=b['receipt']
        if message.get('run_id')!=native['run_id'] or task_id!=native['task_id'] or dispatch_id!=native['dispatch_id']:
            raise Rejected('native worker_done identity mismatch')
        if outcome not in {'succeeded','failed'}:raise Rejected('worker_done outcome must be succeeded or failed')
        packet=self.files.get(b['packet_ref']);result_path=self.files.delivery_path(packet['id']).resolve()
        # Orca defines reportPath as optional long-form display metadata. It is
        # neither an authority field nor a MATS import selector. The immutable
        # binding already identifies the only injected draft MATS may import.
        # Never open or trust the worker-supplied path here.
        if not result_path.is_file():raise Rejected('binding-derived injected delivery draft is missing')
        message_id=message.get('id')
        if not isinstance(message_id,str) or not message_id:raise Rejected('worker_done event lacks a message id')
        completion={'run_id':native['run_id'],'task_id':native['task_id'],'dispatch_id':native['dispatch_id'],
                    'session_id':native['session_id'],'outcome':outcome,'worker_done_verified':True,
                    'source':'MATS normalized native Orca worker_done','simulation':native['simulation']}
        self._completion(b,completion)
        return {'schema_version':9,'delivery_id':delivery_id,'message_id':message_id,'binding_ref':binding_ref,
                'result_path':logical_relative(self.files.root,result_path),'completion':completion,
                'batch_worker_done_dispatches':batch_dispatches,'batch_has_other_events':batch_has_other_events}

    def stage_worker_done_batch(self,messages,delivery_id):
        """Normalize native completion identity into script-owned tmp records."""
        if not isinstance(messages,list):raise Rejected('native event messages must be a list')
        identifier(delivery_id)
        worker=[m for m in messages if isinstance(m,dict) and m.get('type')=='worker_done']
        dispatches=[]
        for message in worker:
            try:payload=json.loads(message.get('payload',''))
            except (TypeError,json.JSONDecodeError) as exc:raise Rejected('worker_done payload is not one JSON object') from exc
            dispatch_id=payload.get('dispatchId') if isinstance(payload,dict) else None
            if not isinstance(dispatch_id,str):raise Rejected('worker_done payload lacks dispatchId')
            identifier(dispatch_id);dispatches.append(dispatch_id)
        if len(set(dispatches))!=len(dispatches):raise Rejected('native batch repeats one worker_done dispatch')
        dispatches=sorted(dispatches);other=len(worker)!=len(messages)
        records=[self._worker_done_record(m,delivery_id,dispatches,other) for m in worker]
        public=[]
        with self.files.lock():
            for record in records:
                dispatch_id=record['completion']['dispatch_id'];path=self.files.completion_event_path(dispatch_id,create=True)
                if path.exists():
                    if load(path)!=record:raise Rejected('conflicting normalized worker_done event')
                else:atomic_write(path,encode(record),immutable=True)
                public.append({'dispatch_id':dispatch_id,'next_operation':{'command':'result','binding_ref':dispatch_id}})
        return public

    def import_staged_result(self,binding_ref):
        """Import the exact injected draft using its script-normalized worker_done."""
        b=self._binding(binding_ref);dispatch_id=b['receipt']['dispatch_id'];path=self.files.completion_event_path(dispatch_id)
        if not path.is_file():raise Rejected('no normalized worker_done for this dispatch; run `mats wait --control` first')
        record=load(path)
        required={'schema_version','delivery_id','message_id','binding_ref','result_path','completion','batch_worker_done_dispatches','batch_has_other_events'}
        if not isinstance(record,dict) or set(record)!=required or record['schema_version']!=9:
            raise Rejected('invalid normalized worker_done staging record')
        if record['binding_ref']!=binding_ref:raise Rejected('normalized worker_done binding mismatch')
        packet=self.files.get(b['packet_ref']);expected=self.files.delivery_path(packet['id']).resolve()
        if record['result_path']!=logical_relative(self.files.root,expected):raise Rejected('normalized worker_done result path mismatch')
        self._completion(b,record['completion'])
        existing=self.files.named('results',dispatch_id)
        result_ref=existing if existing is not None else self.import_result(binding_ref,load(expected),record['completion'])
        return result_ref,record

    def imported_dispatch_ref(self,dispatch_id):
        """Resolve one dispatch to its role-specific canonical delivery collection."""
        identifier(dispatch_id);binding_ref=self.files.named('bindings',dispatch_id)
        if binding_ref is None:return None
        binding=self._binding(binding_ref);role=binding['role']
        if role.startswith('review_'):
            packet=self.files.get(binding['packet_ref']);candidate_ref=packet['candidate_ref']
            ref=self.files.named('reviews',candidate_ref['sha256']+'-'+role)
        else:
            ref=self.files.named('results',dispatch_id)
        if ref is None:return None
        record=self.files.get(ref);completion=record.get('completion') if isinstance(record,dict) else None
        if record.get('binding_ref')!=binding_ref or not isinstance(completion,dict) or completion.get('dispatch_id')!=dispatch_id:
            raise Rejected('canonical delivery identity does not match its dispatch')
        return ref

    def completion_batch_imported(self,record):
        dispatches=record.get('batch_worker_done_dispatches')
        if not isinstance(record.get('batch_has_other_events'),bool) or not isinstance(dispatches,list) or not dispatches:
            raise Rejected('invalid normalized worker_done batch metadata')
        for dispatch_id in dispatches:identifier(dispatch_id)
        if len(set(dispatches))!=len(dispatches):raise Rejected('invalid normalized worker_done batch metadata')
        return not record['batch_has_other_events'] and all(self.imported_dispatch_ref(x) is not None for x in dispatches)

    def clear_completion_batch(self,record):
        """Remove only script-owned tmp inputs after import and native acknowledgement."""
        with self.files.lock():
            for dispatch_id in record['batch_worker_done_dispatches']:
                path=self.files.completion_event_path(dispatch_id);path.unlink(missing_ok=True)
                binding_ref=self.files.named('bindings',dispatch_id)
                if binding_ref:
                    packet=self.files.get(self._binding(binding_ref)['packet_ref'])
                    self.files.delivery_path(packet['id']).unlink(missing_ok=True)
    def verify_candidate(self,c,s=None,*,repo_override=None):
        s=s or self.state();b=self._binding(c['binding_ref']);packet=self.files.get(b['packet_ref']);self._current_contract(s,packet)
        w=self._wp(s,c['wp_id']);repo=Path(repo_override or b['receipt']['workspace_path'])
        self._role_result_contract(packet['role'],c['result'])
        live=self._packet_snapshot(s,packet,w,repo,self._delivery_evidence(c['result']))
        if live['sha256']!=c['result']['snapshot']: raise Rejected('candidate changed after result/R0/review')
        verify_evidence(repo,self._delivery_evidence(c['result']),self.policy(s)['evidence_roots'],workspace_snapshot=live['sha256'])
        return live
    def import_result(self,binding_ref,result,completion):
        b=self._binding(binding_ref);self._completion(b,completion);s=self.state();packet=self.files.get(b['packet_ref']);self._current_contract(s,packet)
        role=b['role']
        existing=self.imported_dispatch_ref(b['receipt']['dispatch_id'])
        if existing:
            old=self.files.get(existing)
            if old['binding_ref']==binding_ref and old['result']==result and old['completion']==completion: return existing
            raise Rejected('immutable dispatch result collision')
        kind='result' if role in OWNERS else 'review' if role.startswith('review_') else 'planner_result' if role=='planner' else 'side_result'
        if completion['outcome']!='succeeded' and (kind in {'review','planner_result'} or result.get('status') in {'candidate','done'}):
            raise Rejected('failed native dispatch cannot attest a successful semantic artifact')
        if kind=='planner_result':
            try:
                validate(kind,result)
            except Rejected as exc:
                feedback=self._record_planner_rejection(binding_ref,packet,result,'output_schema',exc)
                raise Rejected(f'Planner output schema rejected; retry only with repair_of={feedback["path"]}#{feedback["sha256"]}: {exc}') from exc
            try:
                self._planner_semantic_preview(s,b,packet,result)
            except Rejected as exc:
                feedback=self._record_planner_rejection(binding_ref,packet,result,'output_semantics',exc)
                raise Rejected(f'Planner output semantic contract rejected; retry only with repair_of={feedback["path"]}#{feedback["sha256"]}: {exc}') from exc
        else:
            validate(kind,result)
            if role in OWNERS:self._role_result_contract(role,result)
        memo=result.get('source_memo') if isinstance(result,dict) else None
        if isinstance(memo,dict):
            for ref in memo.get('source_refs',[]):self._materialize_internal_ref(ref,prefixes=('results','reviews'))
        if len(encode(result))>max(65536,self.policy(s)['packet_limits'][role]): raise Rejected('oversized result: keep bulk evidence in source artifacts')
        v={'kind':'owner_result' if role in OWNERS else 'review' if kind=='review' else kind,'role':role,'binding_ref':binding_ref,
           'wp_id':packet['wp_id'],'contract_digest':packet['contract_digest'],'plan_version':packet['plan_version'], 'result':result, 'completion':completion}
        if role in OWNERS:
            live=self.verify_candidate(v,s)
            if v['wp_id'] in s['accepted']: raise Rejected('accepted work cannot receive a replacement candidate')
            core=copy.deepcopy(result);core.pop('summary',None);core.pop('snapshot',None);core.pop('consumed_sides',None)
            core['content']={'files':live['manifest']['files'],'worktree':live['manifest']['worktree_diff_sha256'],'index':live['manifest']['index_diff_sha256']}
            core['evidence']=sorted(set(e['sha256'] for e in core['evidence']))
            core['source_memo']['evidence_refs']=sorted(set(e['sha256'] for e in core['source_memo']['evidence_refs']))
            for spec in core.get('recovered_specs',[]):
                spec['subject']=spec['subject']['sha256'];spec['evidence']=sorted(set(e['sha256'] for e in spec['evidence']))
            # Nonce/dispatch/packet/title changes cannot reset an adverse review.
            v['snapshot_manifest']=live['manifest']
            v['work_digest']=digest({'contract':packet['contract_digest'],'result':core})
            prev=s['current_candidates'].get(v['wp_id'])
            if prev and self.files.get(prev)['work_digest']==v['work_digest']:
                raise Rejected('same substantive candidate: reuse prior review; a new dispatch is not new work')
            if result['status']=='candidate': self._validate_consumption(v,s)
        elif kind=='review':
            cref=packet['candidate_ref'];c=self.files.get(cref);self.verify_candidate(c,s)
            if self.verify_candidate(c,s,repo_override=Path(b['receipt']['workspace_path']))['sha256']!=c['result']['snapshot']:
                raise Rejected('reviewer snapshot changed during review')
            if result['target_digest']!=cref['sha256'] or s['current_candidates'].get(v['wp_id'])!=cref:
                raise Rejected('review targets a stale/different candidate')
            if role=='review_r2' and result['outcome'] in {'needs_synthesis','escalate_r2'}: raise Rejected('R2 cannot open another review/synthesis loop')
            if role=='review_r1' and result['outcome']=='needs_synthesis':
                requests=[ref for ref in self.side_requests_for_binding(binding_ref)
                          if self.files.get(ref)['request']['kind']=='synthesis']
                if len(requests)!=1:raise Rejected('R1 needs_synthesis requires exactly one generated Synthesis request before delivery')
                v['side_request_ref']=requests[0]
            if result['outcome']=='plan_conflict' and not result['source_memo']['decision_requested'].strip():
                raise Rejected('reviewer conflict requires reviewer-owned memo')
            for f in result['findings']: verify_evidence(Path(b['receipt']['workspace_path']),f['evidence'],self.policy(s)['evidence_roots'],workspace_snapshot=c['result']['snapshot'])
            verify_evidence(Path(b['receipt']['workspace_path']),result['source_memo']['evidence_refs'],self.policy(s)['evidence_roots'],workspace_snapshot=c['result']['snapshot'])
            v['candidate_ref']=cref
            return self.files.put('reviews',cref['sha256']+'-'+role,v)
        elif kind=='side_result':
            source=self.files.get(packet['request'])
            verify_evidence(Path(b['receipt']['workspace_path']),source['request']['evidence'],self.policy(s)['evidence_roots'])
            verify_evidence(Path(b['receipt']['workspace_path']),result['evidence'],self.policy(s)['evidence_roots'])
            if role=='luna_aux' and result['coverage']['total']==0: raise Rejected('auxiliary must state nonzero coverage denominator')
            v['request_ref']=packet['request'];v['synthesis_fingerprint']=packet.get('synthesis_fingerprint')
        elif kind=='planner_result':
            pass  # schema + cross-field semantic preview already completed above
        with self.files.lock():
            current=self.state();self._current_contract(current,packet)
            ref=self.files.put('results',b['receipt']['dispatch_id'],v)
            if role in OWNERS:
                current['latest_sources'][v['wp_id']]=ref
                if result['status']=='candidate': current['current_candidates'][v['wp_id']]=ref
                else: current['current_candidates'].pop(v['wp_id'],None)
                self.files.commit(current)
            return ref
    def _validate_consumption(self,c,s):
        b=self._binding(c['binding_ref']);packet=self.files.get(b['packet_ref'])
        sides={ref['sha256']:(ref,v) for ref,v in self.files.all('results') if v.get('kind')=='side_result' and v['wp_id']==c['wp_id'] and v['contract_digest']==c['contract_digest'] and v['plan_version']>s['invalidations'].get(c['wp_id'],0)}
        consumed={x['side_ref']['sha256']:x for x in c['result']['consumed_sides']}
        if len(consumed)!=len(c['result']['consumed_sides']) or set(consumed)!=set(sides): raise Rejected('every current side result must be explicitly consumed exactly once')
        for key,item in consumed.items():
            side=self.files.get(item['side_ref'])
            if side!=sides[key][1]: raise Rejected('side result mismatch')
            source=self.files.get(side['request_ref'])
            verify_evidence(Path(b['receipt']['workspace_path']),source['request']['evidence']+side['result']['evidence'],self.policy(s)['evidence_roots'])
            if side['result']['status']!='done' and item['disposition']!='rejected': raise Rejected('blocked/failed advice cannot be accepted')
            if item['disposition']!='rejected' and not item['verified_evidence']: raise Rejected('accepted advice needs owner-verified raw evidence')
            verify_evidence(Path(b['receipt']['workspace_path']),item['verified_evidence'],self.policy(s)['evidence_roots'])
        old=s['current_candidates'].get(c['wp_id'])
        if old:
            r=self.review_record(old,'review_r1')
            if r and r['result']['outcome']=='needs_synthesis':
                if not any(v['role']=='synthesis' and self.files.get(self.files.get(v['request_ref'])['binding_ref'])['packet_ref']==self._binding(r['binding_ref'])['packet_ref'] for _,v in sides.values()):
                    raise Rejected('R1-requested synthesis must bind to that exact R1, then return to owner')
    def r0(self,candidate_ref):
        s=self.state();c=self.files.get(candidate_ref)
        if s['current_candidates'].get(c['wp_id'])!=candidate_ref: raise Rejected('not current candidate')
        before=self.verify_candidate(c,s);w=self._wp(s,c['wp_id']);b=self._binding(c['binding_ref'])
        checks=run_checks(Path(b['receipt']['workspace_path']),w['required_checks'],self.policy(s)['checks'])
        after=self.verify_candidate(c,s)
        if before!=after: raise Rejected('R0 command changed the candidate')
        rec={'candidate_ref':candidate_ref,'snapshot':after['sha256'],'checks':checks,'passed':all(x['passed'] for x in checks),
             'structural_checks':['contract','dependency_bindings','evidence_hashes','candidate_unchanged']}
        return self.files.put('r0',candidate_ref['sha256'],rec)
    def review_record(self,cref,role):
        ref=self.files.named('reviews',cref['sha256']+'-'+role)
        return self.files.get(ref) if ref else None
    def needs_r2(self,c,s,r1=None):
        w=self._wp(s,c['wp_id'])
        tags=set(c['result']['structural_tags'])
        return w['review_policy']=='r2' or w['impact'] in {'cross_boundary','unknown'} or c['result']['impact'] in {'cross_boundary','unknown'} or bool(tags & R2_TRIGGER_TAGS) or bool(r1 and r1['result']['outcome']=='escalate_r2')
    def accept(self,wp_id,view):
        with self.files.lock():
            s=self.state();self._view(s,view);self._control(s)
            ref=s['current_candidates'].get(wp_id)
            if not ref: raise Rejected('no current candidate',code='CANDIDATE_MISSING')
            c=self.files.get(ref);self.verify_candidate(c,s);self._validate_consumption(c,s)
            r0=self.files.named('r0',ref['sha256'])
            if not r0:
                raise Rejected('R0 missing',code='R0_REQUIRED',next_operation={'command':'r0','candidate_ref':ref['path']})
            if not self.files.get(r0)['passed']:
                raise Rejected('R0 failed',code='R0_FAILED',next_operation={'command':'dispatch','operation':'owner','wp':wp_id,'continue_owner':True,'source_ref':r0['path']})
            r1=self.review_record(ref,'review_r1');need=self.needs_r2(c,s,r1)
            if not r1:
                raise Rejected('R1 missing',code='R1_REQUIRED',next_operation={'command':'dispatch','operation':'review_r1','wp':wp_id})
            if r1['result']['outcome'] not in ({'pass','escalate_r2'} if need else {'pass'}):
                raise Rejected('R1 does not permit acceptance',code='R1_OUTCOME_PENDING')
            if need:
                r2=self.review_record(ref,'review_r2')
                if not r2:
                    raise Rejected('passing R2 required',code='R2_REQUIRED',next_operation={'command':'dispatch','operation':'review_r2','wp':wp_id})
                if r2['result']['outcome']!='pass':raise Rejected('R2 does not permit acceptance',code='R2_OUTCOME_PENDING')
            for role in ['review_r1']+(['review_r2'] if need else []):
                r=self.review_record(ref,role);rb=self._binding(r['binding_ref'])
                for f in r['result']['findings']: verify_evidence(Path(rb['receipt']['workspace_path']),f['evidence'],self.policy(s)['evidence_roots'])
            require_drained(view,{wp_id})
            self.verify_candidate(c,s)
            s['accepted'][wp_id]={'candidate_ref':ref,'accepted_under_plan':s['plan']['version'],'review':'r2' if need else 'r1'}
            self.files.commit(s);return s['accepted'][wp_id]
    def apply_plan(self,proposal_ref,view):
        with self.files.lock():
            s=self.state();self._view(s,view);self._control(s);v=self.files.get(proposal_ref)
            if v.get('kind')!='planner_result' or v['role']!='planner': raise Rejected('only bound Planner proposals can change commitments')
            b=self._binding(v['binding_ref']);packet=self.files.get(b['packet_ref']);r=v['result']
            if r['base_plan_version']!=s['plan']['version']: raise Rejected('another plan was committed; explicitly rebase through Planner')
            # Only acceptance identities the Planner actually relied on must remain current.
            observed=packet['accepted_bindings']
            for ref in r['basis_refs']:
                for wid,old in observed.items():
                    if old==ref and s['accepted'].get(wid,{}).get('candidate_ref')!=old: raise Rejected('Planner relied on superseded accepted evidence')
            try:
                new_project,new_plan,affected=self._planner_semantic_preview(s,b,packet,r)
            except Rejected as exc:
                feedback=self._record_planner_rejection(v['binding_ref'],packet,r,'apply_semantics',exc,proposal_ref=proposal_ref)
                raise Rejected(f'Planner proposal rejected at apply; use repair_of only if state remains unchanged: {feedback["path"]}#{feedback["sha256"]}: {exc}') from exc
            invalid=set(r['invalidate_accepted'])
            drain=set(index(new_plan)) if packet['request'].get('target_milestone_id') else affected
            require_drained(view,drain)
            for wid in affected:
                s['accepted'].pop(wid,None);s['current_candidates'].pop(wid,None);s['latest_sources'].pop(wid,None);s['invalidations'][wid]=s['plan']['version']
            self.files.ensure_milestone(new_plan['plan_id'])
            s['project']=new_project;s['plan']=new_plan
            s['last_planner']={'proposal_ref':proposal_ref,'git_head':packet['git_head'],'accepted_bindings':packet['accepted_bindings'],'directive_ids':packet['directive_ids_seen']}
            self.files.commit(s);return {'affected_closure':sorted(affected),'plan_version':s['plan']['version']}

    def planner_drain_set(self,proposal_ref):
        """Recompute the exact closure a current valid Planner proposal must drain."""
        s=self.state();v=self.files.get(proposal_ref)
        if v.get('kind')!='planner_result' or v['role']!='planner':raise Rejected('only bound Planner proposals have a drain set')
        b=self._binding(v['binding_ref']);packet=self.files.get(b['packet_ref']);r=v['result']
        if r['base_plan_version']!=s['plan']['version']:raise Rejected('another plan was committed; explicitly rebase through Planner')
        _new_project,new_plan,affected=self._planner_semantic_preview(s,b,packet,r)
        return set(index(new_plan)) if packet['request'].get('target_milestone_id') else set(affected)
