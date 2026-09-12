import contextlib,copy,io,sys,unittest
from support import *
from common import parse,relative,contained,atomic_write,encode
from contracts import validate,validate_project_plan,patch_impact,contract_digest,planner_contract_checklist
from packets import hydrate
from dispatchctl import main as dispatchctl_main

class StrictContracts(unittest.TestCase):
    @staticmethod
    def interface_spec(binding='required',target='src/transport.go',sid='transport'):
        return {'id':sid,'binding':binding,'language':'go','target_path':target,
                'declarations':['type Transport interface {','Send([]byte) error','Close() error','}'],
                'invariants':['Send preserves one input datagram per frame.'],
                'lifecycle':['Close unblocks pending Send calls.'],
                'compatibility':['Existing UDP mode remains selectable.'],
                'validation':['A compile-time implementation assertion and focused tests pass.'],
                'basis_paths':['src/main.py']}

    def test_engineering_interface_specs_are_optional_but_semantically_bounded(self):
        validate_project_plan(project(),plan())
        p=plan();work=p['work_packages'][0];work.update(owner_role='engineering',required_checks=['unit'],scope={'paths':['src'],'refs':[]})
        work['interface_specs']=[self.interface_spec()]
        validate_project_plan(project(),p)
        work['owner_role']='research'
        with self.assertRaisesRegex(Rejected,'Engineering WPs'):
            validate_project_plan(project(),p)

    def test_interface_spec_ids_and_target_scope_are_checked(self):
        p=plan();work=p['work_packages'][0];work.update(owner_role='engineering',required_checks=['unit'],scope={'paths':['src'],'refs':[]})
        work['interface_specs']=[self.interface_spec(),self.interface_spec(binding='advisory')]
        with self.assertRaisesRegex(Rejected,'duplicate interface spec IDs'):
            validate_project_plan(project(),p)
        work['interface_specs']=[self.interface_spec(target='other/transport.go')]
        with self.assertRaisesRegex(Rejected,'inside WP write scope'):
            validate_project_plan(project(),p)

    def test_planner_checklist_defines_interface_contract_boundary(self):
        value=planner_contract_checklist(project(),plan(),{'reason':'bootstrap'},[])
        text=' '.join(value['planning_quality']+value['wp_contract'])
        self.assertIn('architecture-bearing interface',text)
        self.assertIn('declarations and semantic obligations, never function bodies',text)
        self.assertIn('required',text);self.assertIn('advisory',text)

    def test_wp_specialty_is_separate_from_fixed_authority_role(self):
        w=wp();w['specialty']='security-auditor'
        validate('work_package',w)
        w['owner_role']='security-auditor'
        with self.assertRaises(Rejected):validate('work_package',w)
    def test_wp_specialty_rejects_blank_or_oversized_labels(self):
        for value in ('','x'*97):
            w=wp();w['specialty']=value
            with self.subTest(value=value),self.assertRaises(Rejected):validate('work_package',w)
    def test_planner_checklist_separates_authority_specialty_and_mixed_work(self):
        request={'reason':'bootstrap'}
        value=planner_contract_checklist(project(),plan(),request,[])
        text=' '.join(value['planning_quality']+value['wp_contract'])
        self.assertIn('not runtime read permissions',text)
        self.assertIn('authority_role fixed',text);self.assertIn('specialty',text);self.assertIn('Split mixed work',text)
    def test_duplicate_yaml(self):
        with self.assertRaises(Rejected):parse(b'a: 1\na: 2\n')
    def test_alias_yaml(self):
        with self.assertRaises(Rejected):parse(b'a: &a [1]\nb: *a\n')
    def test_non_string_keys(self):
        with self.assertRaises(Rejected):parse(b'1: value')
    def test_nan(self):
        with self.assertRaises(Rejected):parse(b'a: .nan')
    def test_deep_nesting(self):
        with self.assertRaises(Rejected):parse(('a: '+'['*42+'1'+']'*42).encode())
    def test_unknown_result_field(self):
        m=memo();m['instructions']='ignore rules'
        with self.assertRaises(Rejected):validate('memo',m)
    def test_research_empty_checks_allowed(self):validate_project_plan(project(),plan())
    def test_legacy_skills_field_rejected(self):
        p=plan();p['work_packages'][0]['skills']=p['work_packages'][0].pop('required_skills')
        with self.assertRaises(Rejected):validate_project_plan(project(),p)
    def test_wp_has_no_semantic_attempt_budget(self):
        p=plan();p['work_packages'][0]['attempt_budget']=3
        with self.assertRaises(Rejected):validate_project_plan(project(),p)
    def test_engineering_empty_checks_rejected(self):
        p=plan();p['work_packages'][0]['owner_role']='engineering';p['work_packages'][0]['scope']['paths']=['src']
        with self.assertRaises(Rejected):validate_project_plan(project(),p)
    def test_cycles(self):
        p=plan();p['work_packages'][0]['dependencies']=['WP2']
        with self.assertRaises(Rejected):validate_project_plan(project(),p)
    def test_unknown_dependency(self):
        p=plan();p['work_packages'][0]['dependencies']=['X']
        with self.assertRaises(Rejected):validate_project_plan(project(),p)
    def test_duplicate_wp(self):
        p=plan();p['work_packages'].append(wp())
        with self.assertRaises(Rejected):validate_project_plan(project(),p)
    def test_traversal(self):
        for p in ['../x','x/../y','/tmp/x','x\\y','.task/../x']:
            with self.subTest(path=p),self.assertRaises(Rejected):relative(p)
    def test_control_write_scope(self):
        p=plan();p['work_packages'][0]['scope']['paths']=['.task']
        with self.assertRaises(Rejected):validate_project_plan(project(),p)
    def test_pass_with_major(self):
        r={'schema_version':9,'outcome':'pass','target_digest':'0'*64,'summary':'ok','findings':[{'severity':'major','resolved':False,'detail':'broken','evidence':[]}],'source_memo':memo()}
        with self.assertRaises(Rejected):validate('review',r)
    def test_duplicate_commitment_id(self):
        p=project();p['commitments']*=2
        with self.assertRaises(Rejected):validate_project_plan(p,plan())
    def test_unreferenced_scoped_commitment(self):
        p=project();p['commitments'].append({'id':'C2','statement':'UI only','scope':'scoped','applies_to':['WP3']})
        with self.assertRaises(Rejected):validate_project_plan(p,plan())
    def test_empty_scoped_commitment(self):
        p=project();p['commitments'].append({'id':'C2','statement':'UI','scope':'scoped','applies_to':[]})
        with self.assertRaises(Rejected):validate_project_plan(p,plan())
    def test_commitment_precise_impact(self):
        a=project();b=copy.deepcopy(a);old=plan();new=copy.deepcopy(old);new['version']=2
        b['commitments'].append({'id':'C2','statement':'UI diagnostics','scope':'scoped','applies_to':['WP3']});new['work_packages'][2]['depends_on_commitments']=['C2']
        self.assertEqual(patch_impact(a,old,b,new),{'WP3'})
    def test_global_commitment_affects_all(self):
        a=project();b=copy.deepcopy(a);b['commitments'][0]['statement']='Changed global promise';old=plan();new=copy.deepcopy(old);new['version']=2
        self.assertEqual(patch_impact(a,old,b,new),{'WP1','WP2','WP3'})
    def test_unrelated_metadata_preserves_contract(self):
        a=project();b=copy.deepcopy(a);b['open_questions']=['New exploratory question']
        self.assertEqual(contract_digest(a,wp()),contract_digest(b,wp()))

class CandidateAndReview(Base):
    def test_native_done_does_not_unlock_dependency(self):
        self.candidate()
        with self.assertRaises(Rejected):self.issue(wid='WP2')
    def test_accept_unlocks_dependency(self):self.accepted();self.issue(wid='WP2')
    def test_no_candidate_no_accept(self):
        with self.assertRaises(Rejected):self.g.accept('WP1',self.view())
    def test_no_r0_no_review(self):
        c=self.candidate()
        with self.assertRaises(Rejected):self.review(c)
    def test_no_r1_no_accept(self):
        c=self.candidate();self.g.r0(c)
        with self.assertRaises(Rejected):self.g.accept('WP1',self.view())
    def test_empty_research_domain_checks_have_structural_r0(self):
        c=self.candidate();r=self.g.files.get(self.g.r0(c));self.assertEqual(r['checks'],[]);self.assertTrue(r['passed']);self.assertIn('evidence_hashes',r['structural_checks'])
    def test_r1_failure_blocks(self):
        c=self.candidate();self.g.r0(c);self.review(c,outcome='fix_local')
        with self.assertRaises(Rejected):self.g.accept('WP1',self.view())
    def test_review_shopping_same_candidate(self):
        c=self.candidate();self.g.r0(c);self.review(c,outcome='fix_local')
        with self.assertRaises(Rejected):self.issue('review_r1')
    def test_new_dispatch_summary_not_new_work(self):
        c=self.candidate();self.g.r0(c);self.review(c,outcome='fix_local');b=self.launch(self.issue());r=self.result(b);r['summary']='Different summary'
        with self.assertRaises(Rejected):self.g.import_result(b,r,self.done(b))
    def test_empty_commit_not_new_work(self):
        c=self.candidate();self.g.r0(c);self.review(c,outcome='fix_local');git(self.repo,'commit','--allow-empty','-qm','cosmetic');b=self.launch(self.issue())
        with self.assertRaises(Rejected):self.candidate(b=b)
    def test_source_corrected_candidate_can_be_reviewed(self):
        c=self.candidate();self.g.r0(c);self.review(c,outcome='fix_local');b=self.launch(self.issue());r=self.result(b);r['source_memo']['claims']=['Corrected explanation with explicit assumptions.'];new=self.candidate(b=b,result=r);self.g.r0(new);self.review(new);self.g.accept('WP1',self.view())
    def test_wrong_model_rejected(self):
        pk=self.issue();b=self.launch(pk);r=copy.deepcopy(self.g.files.get(b)['receipt']);r['dispatch_id']='WRONG';r['session_id']='OTHER';r['effective']['model']='gpt-5.6-sol'
        with self.assertRaises(Rejected):self.g.bind(pk,r)
    def test_wrong_effort_rejected(self):
        pk=self.issue();b=self.launch(pk);r=copy.deepcopy(self.g.files.get(b)['receipt']);r['dispatch_id']='WRONG';r['effective']['reasoning_effort']='low'
        with self.assertRaises(Rejected):self.g.bind(pk,r)
    def test_same_owner_continuation_session_allowed(self):
        b=self.launch(self.issue());session=self.g.files.get(b)['receipt']['session_id'];self.candidate(b=b);self.launch(self.issue(),session=session)
    def test_self_review_forbidden(self):
        b=self.launch(self.issue());c=self.candidate(b=b);self.g.r0(c)
        with self.assertRaises(Rejected):self.launch(self.issue('review_r1'),session=self.g.files.get(b)['receipt']['session_id'])
    def test_new_owner_wrong_wp_cannot_reuse_session(self):
        b=self.launch(self.issue());session=self.g.files.get(b)['receipt']['session_id']
        with self.assertRaises(Rejected):self.launch(self.issue(wid='WP3'),session=session)
    def test_wrong_native_completion(self):
        b=self.launch(self.issue());d=self.done(b);d['dispatch_id']='OTHER'
        with self.assertRaises(Rejected):self.g.import_result(b,self.result(b),d)
    def test_failed_native_cannot_claim_candidate(self):
        b=self.launch(self.issue());d=self.done(b);d['outcome']='failed'
        with self.assertRaises(Rejected):self.g.import_result(b,self.result(b),d)
    def test_duplicate_result_is_idempotent(self):
        b=self.launch(self.issue());r=self.result(b);a=self.g.import_result(b,r,self.done(b));self.assertEqual(a,self.g.import_result(b,r,self.done(b)))
    def test_duplicate_binding_is_idempotent(self):
        pk=self.issue();b=self.launch(pk);self.assertEqual(b,self.g.bind(pk,self.g.files.get(b)['receipt']))
    def test_binding_has_script_derived_dispatch_attribution(self):
        pk=self.issue();b=self.launch(pk);binding=self.g.files.get(b)
        self.assertEqual(binding['attribution'],{'reason_code':'OWNER_REQUIRED','operation':'owner','mode':'fresh',
            'source_refs':[],'rework':False,'provider_usage':'unknown'})
    def test_evidence_tamper_blocks_accept(self):
        c=self.candidate();self.g.r0(c);self.review(c);(self.repo/'raw.txt').write_text('Changed')
        with self.assertRaises(Rejected):self.g.accept('WP1',self.view())
    def test_workspace_tamper_blocks_review(self):
        def change(r):
            w=r['plan']['work_packages'][0];w['owner_role']='engineering';w['scope']['paths']=['src'];w['required_checks']=['unit']
        self.g.apply_plan(self.proposal(change),self.view());c=self.candidate();self.g.r0(c);(self.repo/'src/main.py').write_text('VALUE = 2')
        with self.assertRaises(Rejected):self.review(c)
    def test_unresolved_candidate_rejected(self):
        b=self.launch(self.issue());r=self.result(b);r['unresolved']=['Exit condition unknown']
        with self.assertRaises(Rejected):self.candidate(b=b,result=r)
    def test_live_native_wp_blocks_accept(self):
        c=self.candidate();self.g.r0(c);self.review(c)
        with self.assertRaises(Rejected):self.g.accept('WP1',self.view(active=[{'dispatch_id':'LIVE','wp_id':'WP1','role':'research'}]))
    def test_retained_writer_blocks_accept(self):
        c=self.candidate();self.g.r0(c);self.review(c)
        with self.assertRaises(Rejected):self.g.accept('WP1',self.view(users=[{'session_id':'OWNER','workspace_key':'local/main','access':'write','wp_id':'WP1'}]))
    def test_unused_r2_not_dispatched(self):
        c=self.candidate();self.g.r0(c);self.review(c)
        with self.assertRaises(Rejected):self.issue('review_r2')
    def test_r1_escalate_requires_r2(self):
        c=self.candidate();self.g.r0(c);self.review(c,outcome='escalate_r2')
        with self.assertRaises(Rejected):self.g.accept('WP1',self.view())
        self.review(c,'review_r2');self.g.accept('WP1',self.view())
    def test_accept_reports_required_r2_before_requesting_owner_release(self):
        b=self.launch(self.issue());r=self.result(b);r['structural_tags']=['protocol_semantics'];c=self.candidate(b=b,result=r);self.g.r0(c);self.review(c)
        receipt=self.g.files.get(b)['receipt']
        view=self.view(users=[{'session_id':receipt['session_id'],'workspace_key':'local/main','access':'write','wp_id':'WP1'}])
        with self.assertRaisesRegex(Rejected,'^passing R2 required$'):self.g.accept('WP1',view)
    def test_r2_packet_projects_only_selected_tag_definitions(self):
        b=self.launch(self.issue());r=self.result(b);r['structural_tags']=['protocol_semantics','failure_recovery_invariant'];c=self.candidate(b=b,result=r);self.g.r0(c);self.review(c)
        packet=self.g.files.get(self.issue('review_r2'));policy=packet['r2_tag_policy']
        self.assertEqual(policy['projection'],'selected')
        self.assertEqual(set(policy['definitions']),{'protocol_semantics','failure_recovery_invariant'})
        self.assertEqual(policy['non_tag_triggers'],[])
    def test_r2_packet_reports_non_tag_trigger_without_loading_catalog(self):
        c=self.candidate();self.g.r0(c);self.review(c,outcome='escalate_r2')
        policy=self.g.files.get(self.issue('review_r2'))['r2_tag_policy']
        self.assertEqual(policy['projection'],'selected');self.assertEqual(policy['definitions'],{})
        self.assertEqual(policy['non_tag_triggers'],['r1.outcome=escalate_r2'])
    def test_r2_cannot_synthesis_loop(self):
        c=self.candidate();self.g.r0(c);self.review(c,outcome='escalate_r2')
        with self.assertRaises(Rejected):self.review(c,'review_r2','needs_synthesis')
    def test_blocked_new_result_removes_old_candidate(self):
        c=self.candidate();b=self.launch(self.issue());r=self.result(b,'blocked');self.g.import_result(b,r,self.done(b));self.assertNotIn('WP1',self.g.state()['current_candidates'])
    def test_packet_tamper(self):
        pk=self.issue();(self.g.files.root/pk['path']).write_text('changed: true')
        with self.assertRaises(Rejected):self.launch(pk)

class PlanningAndConcurrency(Base):
    def test_milestone_transition_creates_a_new_long_lived_namespace(self):
        accepted=self.accepted();old_path=accepted['path']
        request={'reason':'milestone_audit','question':'Open the transport hardening milestone','source_refs':[accepted],'directive_ids':[],'affected_wp_ids':[],'target_milestone_id':'m1_transport-hardening'}
        proposal=self.proposal(lambda target:target['project'].update(phase='transport-hardening'),request=request)
        self.g.apply_plan(proposal,self.view())
        self.assertEqual(self.g.state()['plan']['plan_id'],'m1_transport-hardening')
        self.assertTrue(old_path.startswith('m0_baseline/results/'))
        self.assertEqual(self.g.files.get(accepted)['wp_id'],'WP1')
        self.assertIn(accepted,[ref for ref,_ in self.g.files.all('results')])
        self.assertTrue(self.issue(wid='WP3')['path'].startswith('m1_transport-hardening/packets/'))
    def test_milestone_number_cannot_skip(self):
        accepted=self.accepted();request={'reason':'milestone_audit','question':'Skip a milestone','source_refs':[accepted],'directive_ids':[],'affected_wp_ids':[],'target_milestone_id':'m2_skipped'}
        with self.assertRaisesRegex(Rejected,'advance exactly once'):self.issue('planner',None,request)
    def test_planner_cannot_relabel_plan_without_request_pinned_milestone(self):
        with self.assertRaisesRegex(Rejected,'target_milestone_id'):
            self.bootstrap_proposal(lambda result:result['plan'].update(plan_id='m1_unpinned'))
    def test_planner_during_unrelated_owner(self):
        uid=self.uid('U');self.g.directive({'id':uid,'raw_text':'Adjust WP3 without touching WP1.','intent':'project_steer'})
        pk=self.issue('planner',None,{'reason':'project_steer','question':'Plan a scoped WP3 adjustment','source_refs':[],'directive_ids':[uid],'affected_wp_ids':['WP3']})
        self.g.preflight(pk,self.view(active=[{'dispatch_id':'OWNER','wp_id':'WP1','role':'research'}]),'snapshot','read_snapshot');self.launch(pk)
    def test_apply_drains_only_affected(self):
        proposal=self.proposal(lambda r:r['plan']['work_packages'][2].update(objective='New UI objective'))
        out=self.g.apply_plan(proposal,self.view(active=[{'dispatch_id':'OWNER','wp_id':'WP1','role':'research'}]));self.assertEqual(out['affected_closure'],['WP3'])
    def test_affected_live_apply_rejected(self):
        proposal=self.proposal(lambda r:r['plan']['work_packages'][0].update(objective='New semantics'))
        with self.assertRaises(Rejected):self.g.apply_plan(proposal,self.view(active=[{'dispatch_id':'OWNER','wp_id':'WP2','role':'engineering'}]))
    def test_unaffected_owner_result_survives_plan_version(self):
        b=self.launch(self.issue());pr=self.proposal(lambda r:r['plan']['work_packages'][2].update(objective='Unrelated change'));self.g.apply_plan(pr,self.view());c=self.candidate(b=b);self.g.r0(c);self.review(c);self.g.accept('WP1',self.view())
    def test_affected_old_owner_fenced(self):
        b=self.launch(self.issue());pr=self.proposal(lambda r:r['plan']['work_packages'][0].update(objective='Different contract'));self.g.apply_plan(pr,self.view())
        with self.assertRaises(Rejected):self.candidate(b=b)
    def test_accepted_change_needs_explicit_invalidation(self):
        self.accepted()
        with self.assertRaises(Rejected):self.proposal(lambda r:r['plan']['work_packages'][0].update(objective='Different contract'))
        self.assertEqual(len(self.g.files.all('planner_rejections')),1)
    def test_transitive_accepted_invalidation(self):
        self.accepted();self.accepted('WP2')
        def change(r):r['plan']['work_packages'][0]['objective']='Different';r['invalidate_accepted']=['WP1']
        with self.assertRaises(Rejected):self.proposal(change)
        self.assertEqual(len(self.g.files.all('planner_rejections')),1)
    def test_explicit_closure_invalidated(self):
        self.accepted();self.accepted('WP2')
        def change(r):r['plan']['work_packages'][0]['objective']='Different';r['invalidate_accepted']=['WP1','WP2']
        pr=self.proposal(change);self.g.apply_plan(pr,self.view());self.assertEqual(self.g.state()['accepted'],{})
    def test_stale_plan_proposal_rejected(self):
        a=self.proposal();b=self.proposal();self.g.apply_plan(a,self.view())
        with self.assertRaises(Rejected):self.g.apply_plan(b,self.view())
    def test_precise_commitment_preserves_accepted_research(self):
        old=self.accepted()
        def change(r):
            r['project']['commitments'].append({'id':'C17','statement':'UI diagnostics','scope':'scoped','applies_to':['WP3']});r['plan']['work_packages'][2]['depends_on_commitments']=['C17']
        pr=self.proposal(change);self.g.apply_plan(pr,self.view());self.assertEqual(self.g.state()['accepted']['WP1']['candidate_ref'],old)
    def test_runtime_planner_patch_updates_only_named_wp(self):
        new_wp=copy.deepcopy(wp('WP3'));new_wp['objective']='New UI objective'
        pr=self.patch_proposal(plan_patch={'work_packages':{'upsert':[new_wp],'remove':[]}},affected=['WP3'])
        out=self.g.apply_plan(pr,self.view());self.assertEqual(out['affected_closure'],['WP3']);self.assertEqual(self.g.state()['plan']['work_packages'][2]['objective'],'New UI objective')
    def test_runtime_planner_full_restatement_rejected(self):
        uid=self.uid('U');self.g.directive({'id':uid,'raw_text':'Change the project','intent':'project_steer'})
        req={'reason':'project_steer','question':'Change','source_refs':[],'directive_ids':[uid],'affected_wp_ids':[]}
        b=self.launch(self.issue('planner',None,req));state=self.g.state();r={'schema_version':9,'mode':'full','base_plan_version':state['plan']['version'],'basis_refs':[],
          'project':copy.deepcopy(state['project']),'plan':copy.deepcopy(state['plan']),'invalidate_accepted':[],'reason':'bad runtime restatement'};r['plan']['version']+=1
        with self.assertRaises(Rejected):self.g.import_result(b,r,self.done(b))
        self.assertEqual(len(self.g.files.all('planner_rejections')),1)
    def test_bootstrap_is_initial_only(self):
        self.launch(self.issue())
        with self.assertRaises(Rejected):self.issue('planner',None,{'reason':'bootstrap','question':'Initial plan','source_refs':[],'directive_ids':[],'affected_wp_ids':[]})
    def test_bootstrap_requires_whole_project_scope(self):
        with self.assertRaises(Rejected):self.issue('planner',None,{'reason':'bootstrap','question':'Initial plan','source_refs':[],'directive_ids':[],'affected_wp_ids':['WP1']})
    def test_bootstrap_planner_patch_rejected(self):
        req={'reason':'bootstrap','question':'Initial plan','source_refs':[],'directive_ids':[],'affected_wp_ids':[]}
        b=self.launch(self.issue('planner',None,req));s0=self.g.state();r={'schema_version':9,'mode':'patch','base_plan_version':s0['plan']['version'],'basis_refs':[],
          'project_patch':{'set':{},'commitments':{'upsert':[],'remove':[]}},'plan_patch':{'work_packages':{'upsert':[],'remove':[]}},'invalidate_accepted':[],'reason':'bad bootstrap patch'}
        with self.assertRaises(Rejected):self.g.import_result(b,r,self.done(b))
        self.assertEqual(len(self.g.files.all('planner_rejections')),1)
    def test_bootstrap_contract_rejection_allows_exact_fresh_repair_without_reset(self):
        req={'reason':'bootstrap','question':'Frame coarse project and Work Packages','source_refs':[],'directive_ids':[],'affected_wp_ids':[]}
        b=self.launch(self.issue('planner',None,req));st=self.g.state();bad={'schema_version':9,'mode':'full','base_plan_version':st['plan']['version'],'basis_refs':[],
            'project':copy.deepcopy(st['project']),'plan':copy.deepcopy(st['plan']),'invalidate_accepted':[],'reason':'bad coverage'}
        bad['plan']['version']+=1;bad['plan']['work_packages'][0]['depends_on_commitments']=['C1']
        with self.assertRaises(Rejected):self.g.import_result(b,bad,self.done(b))
        rej_ref,rej=self.g.files.all('planner_rejections')[0]
        self.assertIn('commitment forward/reverse coverage mismatch',rej['detail']);self.assertTrue(rej['repairable'])
        repair=copy.deepcopy(req);repair['repair_of']=rej_ref
        pk=self.issue('planner',None,repair);body=hydrate(self.g.files,pk)
        self.assertEqual(body['request']['repair_of'],rej_ref)
        self.assertEqual(body['planner_repair_feedback']['result_digest'],rej['result_digest'])
        self.assertIn('Global commitments',body['planner_contract_checklist']['commitment_coverage'][0])
        self.assertEqual(body['planner_contract_checklist']['current_commitment_coverage_map']['global_commitment_ids'],['C1'])
        self.assertEqual(body['planner_contract_checklist']['current_commitment_coverage_map']['current_expected_depends_on_commitments']['WP1'],[])
        self.assertTrue(any('coarse ownership' in x for x in body['planner_contract_checklist']['planning_quality']))
        rb=self.launch(pk);self.assertNotEqual(self.g.files.get(rb)['receipt']['session_id'],self.g.files.get(b)['receipt']['session_id'])

    def test_planner_repair_cli_copies_exact_occasion_and_only_adds_repair_ref(self):
        req={'reason':'bootstrap','question':'Initial coarse plan','source_refs':[],'directive_ids':[],'affected_wp_ids':[]}
        b=self.launch(self.issue('planner',None,req));st=self.g.state();bad={'schema_version':9,'mode':'patch','base_plan_version':st['plan']['version'],'basis_refs':[],
          'project_patch':{'set':{},'commitments':{'upsert':[],'remove':[]}},'plan_patch':{'work_packages':{'upsert':[],'remove':[]}},'invalidate_accepted':[],'reason':'bad'}
        with self.assertRaises(Rejected):self.g.import_result(b,bad,self.done(b))
        rej_ref,rej=self.g.files.all('planner_rejections')[0]
        buf=io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc=dispatchctl_main(['--repo',str(self.repo),'planner-repair',str(self.g.files.root/rej_ref['path']),'--sha256',rej_ref['sha256']])
        self.assertEqual(rc,0)
        out=parse(buf.getvalue().encode());repair=load(out['repair_request_path'])
        for k in ('reason','question','source_refs','directive_ids','affected_wp_ids'):
            self.assertEqual(repair[k],req[k])
        self.assertEqual(repair['repair_of'],rej_ref)
        self.assertEqual(out['planning_occasion'],{k:req[k] for k in ('reason','question','source_refs','directive_ids','affected_wp_ids')})
        self.assertEqual(rej['request'],req)

    def test_planner_repair_cannot_broaden_original_occasion_or_reuse_feedback(self):
        req={'reason':'bootstrap','question':'Initial coarse plan','source_refs':[],'directive_ids':[],'affected_wp_ids':[]}
        b=self.launch(self.issue('planner',None,req));st=self.g.state();bad={'schema_version':9,'mode':'patch','base_plan_version':st['plan']['version'],'basis_refs':[],
          'project_patch':{'set':{},'commitments':{'upsert':[],'remove':[]}},'plan_patch':{'work_packages':{'upsert':[],'remove':[]}},'invalidate_accepted':[],'reason':'bad'}
        with self.assertRaises(Rejected):self.g.import_result(b,bad,self.done(b))
        rej_ref,_=self.g.files.all('planner_rejections')[0]
        broaden=copy.deepcopy(req);broaden['repair_of']=rej_ref;broaden['question']='Also redesign deployment'
        with self.assertRaises(Rejected):self.issue('planner',None,broaden)
        exact=copy.deepcopy(req);exact['repair_of']=rej_ref
        self.issue('planner',None,exact)
        with self.assertRaises(Rejected):self.issue('planner',None,exact)

    def test_prior_rejected_bootstrap_requires_repair_ref_not_reinitialize_logic(self):
        req={'reason':'bootstrap','question':'Initial coarse plan','source_refs':[],'directive_ids':[],'affected_wp_ids':[]}
        b=self.launch(self.issue('planner',None,req));st=self.g.state();bad={'schema_version':9,'mode':'patch','base_plan_version':st['plan']['version'],'basis_refs':[],
          'project_patch':{'set':{},'commitments':{'upsert':[],'remove':[]}},'plan_patch':{'work_packages':{'upsert':[],'remove':[]}},'invalidate_accepted':[],'reason':'bad'}
        with self.assertRaises(Rejected):self.g.import_result(b,bad,self.done(b))
        with self.assertRaises(Rejected) as cm:self.issue('planner',None,req)
        self.assertIn('repair_of',str(cm.exception));self.assertIn('never by reinitializing .task',str(cm.exception))

    def test_reviewer_source_goes_directly_to_planner(self):
        c=self.candidate();self.g.r0(c);rev=self.review(c,outcome='plan_conflict')
        req={'reason':'plan_conflict','question':'Revise invalid commitment','source_refs':[rev],'directive_ids':[],'affected_wp_ids':['WP1']}
        pk=self.issue('planner',None,req);body=hydrate(self.g.files,pk);self.assertEqual(body['source_artifacts'][0],self.g.files.get(rev))
    def test_review_conflict_cannot_local_retry(self):
        c=self.candidate();self.g.r0(c);self.review(c,outcome='plan_conflict')
        with self.assertRaises(Rejected):self.issue()
    def test_unknown_directive_not_automatic_planner(self):
        self.g.directive({'id':'U','raw_text':'Can you explain this?','intent':'unknown'})
        with self.assertRaises(Rejected):self.issue('planner',None,{'reason':'project_steer','question':'Change?','source_refs':[],'directive_ids':['U'],'affected_wp_ids':[]})
    def test_raw_directive_preserved(self):
        raw='Keep exactly this text:\nDo NOT deploy.\n';self.g.directive({'id':'U','raw_text':raw,'intent':'project_steer'});pk=self.issue('planner',None,{'reason':'project_steer','question':'Apply user steering','source_refs':[],'directive_ids':['U'],'affected_wp_ids':[]});self.assertEqual(hydrate(self.g.files,pk)['directives'][0]['raw_text'],raw)
    def test_planner_packet_contains_since_delta(self):
        cref=self.accepted();pk=self.issue('planner',None,{'reason':'milestone_audit','question':'Review accepted impact','source_refs':[cref],'directive_ids':[],'affected_wp_ids':['WP1']});p=hydrate(self.g.files,pk);self.assertNotIn('accepted_delta',p);self.assertNotIn('architecture_api_paths',p['since_last_planner']);self.assertIn('changed_paths',p['since_last_planner']);allp=hydrate(self.g.files,pk,include_available=True);delta=allp['accepted_delta'][0];self.assertEqual(delta['wp_id'],'WP1')
        for field in ('snapshot_manifest','binding_ref','completion','snapshot','evidence'):self.assertNotIn(field,delta['source_result'])
    def test_large_planner_payload_lossless(self):
        with self.g.files.lock():
            s=self.g.state();s['project']['open_questions']=['X'*140000];self.g.files.commit(s)
        pk=self.issue('planner',None,{'reason':'bootstrap','question':'Plan','source_refs':[],'directive_ids':[],'affected_wp_ids':[]});p=self.g.files.get(pk);self.assertTrue(p['required_payload_refs']);self.assertLess(len(encode(p)),131072);self.assertEqual(hydrate(self.g.files,pk)['project']['open_questions'],['X'*140000])
    def test_stale_attachment_rejected(self):
        with self.g.files.lock():
            s=self.g.state();s['project']['open_questions']=['X'*140000];self.g.files.commit(s)
        pk=self.issue('planner',None,{'reason':'bootstrap','question':'Plan','source_refs':[],'directive_ids':[],'affected_wp_ids':[]});p=self.g.files.get(pk);att=p['required_payload_refs'][-1]['ref'];(self.g.files.root/att['path']).write_text('tampered: true')
        with self.assertRaises(Rejected):hydrate(self.g.files,pk)

if __name__=='__main__':unittest.main()

class MaterializedStateReadModel(Base):
    def test_packet_marks_materialized_current_view(self):
        pk=self.issue()
        p=self.g.files.get(pk)
        self.assertTrue(p['state_view']['materialized'])
        self.assertEqual(p['state_view']['plan_version'], self.g.state()['plan']['version'])
        self.assertEqual(p['state_view']['semantic_digest'], digest(self.g.state()))

    def test_runtime_patch_materializes_before_next_owner_packet(self):
        def mutate(target):
            target['plan']['work_packages'][0]['objective']='Updated objective from runtime patch'
        prop=self.proposal(mutate=mutate)
        self.g.apply_plan(prop,self.view())
        current=self.g.state()
        self.assertEqual(next(w for w in current['plan']['work_packages'] if w['id']=='WP1')['objective'],'Updated objective from runtime patch')
        pk=self.issue()
        packet=self.g.files.get(pk)
        self.assertEqual(packet['work_package']['objective'],'Updated objective from runtime patch')
        self.assertEqual(packet['state_view']['semantic_digest'],digest(current))

    def test_planner_reads_current_materialized_state_not_patch_history(self):
        prop=self.proposal(mutate=lambda target: target['project'].__setitem__('phase','engineering'))
        self.g.apply_plan(prop,self.view())
        uid=self.uid('U');self.g.directive({'id':uid,'raw_text':'Reconsider the next milestone.','intent':'project_steer'})
        req={'reason':'project_steer','question':'Reconsider the next milestone','source_refs':[],'directive_ids':[uid],'affected_wp_ids':[]}
        pk=self.issue('planner',None,req)
        packet=hydrate(self.g.files,pk)
        self.assertEqual(packet['project']['phase'],'engineering')
        self.assertNotIn('planner_history',packet)
        self.assertNotIn('patch_history',packet)
        self.assertTrue(packet['state_view']['materialized'])
