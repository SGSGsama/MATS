import copy,unittest
from unittest.mock import patch
from support import *
from common import encode
import routing
from routing import R2_TRIGGER_TAGS,admission,launch_argv,route_side,next_review,validate_policy,validate_operator
from contracts import catalog
from role_spawn import spawn

class NativeAdmission(Base):
    def test_independent_owner_parallel(self):
        pk=self.issue(wid='WP3');v=self.view(active=[{'dispatch_id':'D1','wp_id':'WP1','role':'research'}]);self.g.preflight(pk,v,'local/other','read_snapshot')
    def test_independent_worktree_writers_parallel(self):
        v=self.view(users=[{'session_id':'S1','workspace_key':'local/A','access':'write','wp_id':'WP1'}]);admission(v,'P','RUN','engineering','WP3','local/B','write')
    def test_same_worktree_writer_rejected(self):
        v=self.view(users=[{'session_id':'S1','workspace_key':'local/A','access':'write','wp_id':'WP1'}])
        with self.assertRaises(Rejected):admission(v,'P','RUN','engineering','WP3','local/A','write')
    def test_read_snapshot_parallel_to_writer(self):
        v=self.view(users=[{'session_id':'S1','workspace_key':'local/A','access':'write','wp_id':'WP1'}]);admission(v,'P','RUN','research','WP3','local/A','read_snapshot')
    def test_live_reader_conflicts_with_writer(self):
        v=self.view(users=[{'session_id':'S1','workspace_key':'local/A','access':'write','wp_id':'WP1'}])
        with self.assertRaises(Rejected):admission(v,'P','RUN','research','WP3','local/A','read_live')
    def test_writer_conflicts_with_live_reader(self):
        v=self.view(users=[{'session_id':'S1','workspace_key':'local/A','access':'read_live','wp_id':'WP1'}])
        with self.assertRaises(Rejected):admission(v,'P','RUN','engineering','WP3','local/A','write')
    def test_same_wp_second_owner_rejected(self):
        v=self.view(active=[{'dispatch_id':'LIVE','wp_id':'WP1','role':'research'}])
        with self.assertRaises(Rejected):self.g.preflight(self.issue(),v,'local/B','read_snapshot')
    def test_native_view_incomplete_rejected(self):
        v=self.view();v['complete']=False
        with self.assertRaises(Rejected):self.g.preflight(self.issue(),v,'local/A','read_snapshot')
    def test_native_view_wrong_run_rejected(self):
        v=self.view();v['run_id']='OTHER'
        with self.assertRaises(Rejected):self.g.preflight(self.issue(),v,'local/A','read_snapshot')
    def test_native_view_live_sim_mismatch_rejected(self):
        v=self.view();v['simulation']=False
        with self.assertRaises(Rejected):self.g.preflight(self.issue(),v,'local/A','read_snapshot')
    def test_optional_parallel_cap(self):
        v=self.view(active=[{'dispatch_id':'D','wp_id':'WP3','role':'research'}])
        with self.assertRaises(Rejected):admission(v,'P','RUN','research','WP1','local/A','read_snapshot',max_parallel=1)
    def test_side_role_write_denied(self):
        with self.assertRaises(Rejected):admission(self.view(),'P','RUN','synthesis','WP1','local/A','write')
    def test_failed_reply_never_auto_retries(self):
        calls=[]
        def start(argv):calls.append(argv);raise OSError('unknown native delivery')
        with patch('role_spawn.ensure_run_context',return_value={'action':'already_bound','run_id':'RUN'}), patch('role_spawn.create_task',return_value={'result':{'task':{'id':'T'}}}), patch('role_spawn.start_worker',side_effect=start):
            with self.assertRaises(OSError):
                spawn(self.g,name='LOST',operation='owner',wp='WP1',request=None,worktree='current',cli='orca',instructions='',runtime_view=self.view(),workspace_key='local/A',access='read_snapshot')
        self.assertEqual(len(calls),1);self.assertFalse(self.g.files.all('bindings'))
    def test_incomplete_view_never_starts(self):
        v=self.view();v['complete']=False
        with patch('role_spawn.ensure_run_context') as native:
            with self.assertRaises(Rejected):
                spawn(self.g,name='INCOMPLETE',operation='owner',wp='WP1',request=None,worktree='current',cli='orca',instructions='',runtime_view=v,workspace_key='local/A',access='read_snapshot')
        native.assert_not_called()
    def test_same_packet_unknown_delivery_cannot_restart(self):
        pk=self.issue();self.launch(pk)
        with self.assertRaises(Rejected):self.g.preflight(pk,self.view(),'local/A','read_snapshot')
    def test_same_packet_native_failed_retry_allowed(self):
        pk=self.issue();b=self.launch(pk);v=self.view();v['settled_dispatches']=[{'dispatch_id':self.g.files.get(b)['receipt']['dispatch_id'],'outcome':'failed'}]
        self.g.preflight(pk,v,'local/A','read_snapshot')
    def test_same_packet_native_success_cannot_retry(self):
        pk=self.issue();b=self.launch(pk);v=self.view();v['settled_dispatches']=[{'dispatch_id':self.g.files.get(b)['receipt']['dispatch_id'],'outcome':'succeeded'}]
        with self.assertRaises(Rejected):self.g.preflight(pk,v,'local/A','read_snapshot')
    def test_lock_prevents_launch_apply_race(self):
        with self.g.files.lock():
            with self.assertRaises(Rejected):
                spawn(self.g,name='LOCKED',operation='owner',wp='WP1',request=None,worktree='current',cli='definitely-not-orca',instructions='',runtime_view=self.view(),workspace_key='local/A',access='read_snapshot')

    def test_plan_apply_uses_same_admission_lock_as_dispatch(self):
        proposal=self.proposal()
        with self.g.files.lock():
            with self.assertRaises(Rejected):self.g.apply_plan(proposal,self.view())

    def test_accept_uses_same_admission_lock_as_dispatch(self):
        candidate=self.candidate();self.g.r0(candidate);self.review(candidate)
        with self.g.files.lock():
            with self.assertRaises(Rejected):self.g.accept('WP1',self.view())

class SemanticRouting(Base):
    def test_side_source_owner_only(self):
        b=self.launch(self.issue());ref=self.side(b);req=self.g.files.get(ref)['request']
        with self.assertRaises(Rejected):self.g.side_request(b,req,caller_session='SCONTROL')
    def test_luna_class_cannot_be_named_synthesis(self):
        b=self.launch(self.issue());ref=self.side(b,'luna_aux');req=self.g.files.get(ref)['request'];req['kind']='synthesis'
        with self.assertRaises(Rejected):route_side(req)
    def test_synthesis_requires_attempt(self):
        b=self.launch(self.issue());ref=self.side(b);req=self.g.files.get(ref)['request'];req['attempted']=[]
        with self.assertRaises(Rejected):route_side(req)
    def test_synthesis_not_commitment_detour(self):
        b=self.launch(self.issue());ref=self.side(b);req=self.g.files.get(ref)['request'];req['affected_commitments']=['C1']
        with self.assertRaises(Rejected):route_side(req)
    def test_side_verifiability_required(self):
        b=self.launch(self.issue());ref=self.side(b);req=self.g.files.get(ref)['request'];req['verification_plan']=' '
        with self.assertRaises(Rejected):route_side(req)
    def test_synthesis_same_decision_no_repeat(self):
        b=self.launch(self.issue());req=self.side(b);self.launch(self.issue('synthesis',request=req))
        with self.assertRaises(Rejected):self.issue('synthesis',request=req)
    def test_synthesis_renamed_source_not_new_evidence(self):
        b=self.launch(self.issue());req=self.side(b);self.launch(self.issue('synthesis',request=req));value=self.g.files.get(req)['request'];(self.repo/'alias.txt').write_text((self.repo/'raw.txt').read_text());value['evidence'][0]['path']='alias.txt';value['question']='Paraphrased question';new=self.g.side_request(b,value,caller_session=self.g.files.get(b)['receipt']['session_id'])
        with self.assertRaises(Rejected):self.issue('synthesis',request=new)
    def test_aux_return_not_automatic_acceptance(self):
        owner=self.launch(self.issue());req=self.side(owner,'luna_aux');side=self.launch(self.issue('luna_aux',request=req));self.side_result(side)
        with self.assertRaises(Rejected):self.candidate(b=owner)
    def test_owner_consumes_aux_evidence(self):
        owner=self.launch(self.issue());req=self.side(owner,'luna_aux');side=self.launch(self.issue('luna_aux',request=req));sref=self.side_result(side);r=self.result(owner);r['consumed_sides']=[{'side_ref':sref,'disposition':'accepted','reason':'Checked raw records','verified_evidence':self.evidence()}];c=self.candidate(b=owner,result=r);self.g.r0(c);self.review(c);self.g.accept('WP1',self.view())
    def test_consumption_without_evidence_rejected(self):
        owner=self.launch(self.issue());req=self.side(owner,'luna_aux');side=self.launch(self.issue('luna_aux',request=req));sref=self.side_result(side);r=self.result(owner);r['consumed_sides']=[{'side_ref':sref,'disposition':'accepted','reason':'Trust it','verified_evidence':[]}]
        with self.assertRaises(Rejected):self.candidate(b=owner,result=r)
    def test_r1_synthesis_returns_to_owner_not_r2(self):
        owner=self.launch(self.issue());c=self.candidate(b=owner);self.g.r0(c);review=self.review(c,outcome='needs_synthesis');rb=self.g.files.get(review)['binding_ref'];req=self.side(rb);sb=self.launch(self.issue('synthesis',request=req));sref=self.side_result(sb);b=self.launch(self.issue(),session=self.g.files.get(owner)['receipt']['session_id']);r=self.result(b);r['source_memo']['claims']=['Resolved ambiguity against the raw record.'];r['consumed_sides']=[{'side_ref':sref,'disposition':'accepted','reason':'Verified decisive observation','verified_evidence':self.evidence()}];new=self.candidate(b=b,result=r);self.g.r0(new);self.review(new);self.g.accept('WP1',self.view())
    def test_old_synthesis_cannot_satisfy_new_r1(self):
        owner=self.launch(self.issue());req=self.side(owner);sb=self.launch(self.issue('synthesis',request=req));sref=self.side_result(sb);r=self.result(owner);r['consumed_sides']=[{'side_ref':sref,'disposition':'accepted','reason':'Checked','verified_evidence':self.evidence()}];c=self.candidate(b=owner,result=r);self.g.r0(c);self.review(c,outcome='needs_synthesis');b=self.launch(self.issue());r2=self.result(b);r2['source_memo']['claims']=['Try to claim old advice resolves new question'];r2['consumed_sides']=r['consumed_sides']
        with self.assertRaises(Rejected):self.candidate(b=b,result=r2)
    def test_synthesis_author_cannot_be_r2(self):
        owner=self.launch(self.issue());req=self.side(owner);sb=self.launch(self.issue('synthesis',request=req));sref=self.side_result(sb);r=self.result(owner);r['consumed_sides']=[{'side_ref':sref,'disposition':'accepted','reason':'Checked','verified_evidence':self.evidence()}];c=self.candidate(b=owner,result=r);self.g.r0(c);self.review(c,outcome='escalate_r2')
        with self.assertRaises(Rejected):self.launch(self.issue('review_r2'),session=self.g.files.get(sb)['receipt']['session_id'])
    def test_direct_model_override_operation_rejected(self):
        with self.assertRaises(Rejected):self.issue('gpt-6-astra')
    def test_review_next_actions_distinct(self):
        expected={'pass':'accept_or_r2','fix_local':'owner','needs_synthesis':'synthesis_then_owner','escalate_r2':'review_r2','plan_conflict':'planner'}
        self.assertEqual({k:next_review(k) for k in expected},expected)
    def test_control_model_mismatch_rejected(self):
        r=self.g.files.get(self.g.state()['control_ref']);r['effective']['model']='gpt-6-astra'
        with self.assertRaises(Rejected):self.g.attach_control(r)
    def test_api_efforts_not_silently_downgraded(self):
        args=launch_argv(self.policy,'luna_aux','T','current');self.assertEqual(args[args.index('--effort')+1],'max')
    def test_native_launch_pins_models(self):
        for role,b in self.policy['bindings'].items():
            if role=='control':continue
            args=launch_argv(self.policy,role,'T','current');self.assertEqual(args[args.index('--model')+1],b['model']);self.assertIn('--effort',args)
    def test_cyber_replaces_only_sol_and_preserves_effort(self):
        for role in ('synthesis','review_r2'):
            plan=routing.dispatch_bindings(self.policy,role,cyber=True)
            self.assertEqual(plan['primary'],{'model':'gpt-daybreak-blue-latest','reasoning_effort':'high'})
            self.assertEqual(plan['fallback'],{'model':'gpt-5.6-sol','reasoning_effort':'high'})
            args=launch_argv(self.policy,role,'T','current',cyber=True)
            self.assertEqual(args[args.index('--model')+1],'gpt-daybreak-blue-latest')
            self.assertEqual(args[args.index('--effort')+1],'high')
        terra=routing.dispatch_bindings(self.policy,'research',cyber=True)
        self.assertEqual(terra['primary'],fixed_binding(self.policy,'research'))
        self.assertIsNone(terra['fallback'])
    def test_cyber_packet_rejects_unattested_sol_binding(self):
        owner=self.launch(self.issue());request=self.side(owner,'synthesis')
        packet=self.g.issue(self.uid('CYBER'),'synthesis',wp_id='WP1',request=request,cyber=True)
        with self.assertRaises(Rejected):self.launch(packet)
    def test_cyber_packet_accepts_attested_daybreak_blue_binding(self):
        owner=self.launch(self.issue());request=self.side(owner,'synthesis')
        packet=self.g.issue(self.uid('CYBER'),'synthesis',wp_id='WP1',request=request,cyber=True)
        receipt={'schema_version':9,'run_id':'RUN','task_id':self.uid('T'),'dispatch_id':self.uid('D'),'session_id':self.uid('S'),'workspace_key':'local/main','workspace_path':str(self.repo),'access':'read_snapshot','fresh_context':True,'effective':{'model':'gpt-daybreak-blue-latest','reasoning_effort':'high'},'packet_digest':packet['sha256'],'source':'simulated native launch','simulation':True}
        self.assertIn('/bindings/',self.g.bind(packet,receipt)['path'])
    def test_owner_reuse_does_not_send_incompatible_flags(self):
        args=launch_argv(self.policy,'research','T','current',terminal='term',reuse_receipt={'effective':fixed_binding(self.policy,'research'),'workspace_key':'local/main'});self.assertIn('--terminal',args);self.assertIn('id:local/main',args);self.assertNotIn('--model',args);self.assertNotIn('--effort',args)
    def test_control_not_a_supervised_child_coordinator(self):
        with self.assertRaises(Rejected):launch_argv(self.policy,'control','T','current')
    def test_reviewer_cannot_terminal_reuse(self):
        with self.assertRaises(Rejected):launch_argv(self.policy,'review_r1','T','current',terminal='term',reuse_receipt={'effective':fixed_binding(self.policy,'review_r1')})
    def test_observe_budget_not_false_enforcement(self):
        p=copy.deepcopy(self.policy);p['budget_mode']='enforce'
        with self.assertRaises(Rejected):validate_policy(p)

    def test_fixed_policy_rejects_binding_and_identity_changes(self):
        p=copy.deepcopy(self.policy);p['bindings']['research']['model']='gpt-6-astra'
        with self.assertRaises(Rejected):validate_policy(p)
        p=copy.deepcopy(self.policy);p['policy_id']='replacement-policy'
        with self.assertRaises(Rejected):validate_policy(p)

    def test_policy_rejects_unsafe_paths_and_malformed_check_catalog(self):
        p=copy.deepcopy(self.policy);p['structural_paths']=['..\\security']
        with self.assertRaises(Rejected):validate_policy(p)
        p=copy.deepcopy(self.policy);p['checks']={'unit':{'argv':'python -m unittest','timeout_seconds':10}}
        with self.assertRaises(Rejected):validate_policy(p)

    def test_schema_and_guard_share_closed_r2_trigger_tags(self):
        schema_tags=catalog()['$defs']['result']['properties']['structural_tags']['items']['enum']
        self.assertEqual(set(schema_tags),R2_TRIGGER_TAGS)
        self.assertFalse({'major_change','security_critical','critical_execution_chain'} & R2_TRIGGER_TAGS)
        reference=load(ROOT/'skill/multi-agent-task-split/references/r2-tags.yaml')
        self.assertEqual(set(reference['tags']),R2_TRIGGER_TAGS)
        for definition in reference['tags'].values():self.assertEqual(set(definition),{'trigger','exclude','audit'})


class OperatorCapPolicy(Base):
    def test_default_owner_candidate_cap_is_unbounded(self):
        for _ in range(6):
            b=self.launch(self.issue());self.g.import_result(b,self.result(b,'blocked'),self.done(b))
        self.assertIsNotNone(self.issue())
    def test_operator_caps_are_not_semantic_policy(self):
        self.assertNotIn('operator_limits',self.policy)
        value=self.g.operator();self.assertEqual(value['caps']['max_parallel_operations'],4)
    def test_operator_cap_update_is_independent(self):
        value=copy.deepcopy(self.g.operator());value['caps']['max_owner_candidates_per_wp']=1;self.g.set_operator(value)
        b=self.launch(self.issue());self.g.import_result(b,self.result(b,'blocked'),self.done(b))
        with self.assertRaises(Rejected):self.issue()
    def test_operator_update_serializes_with_dispatch_admission(self):
        value=copy.deepcopy(self.g.operator());value['caps']['max_parallel_operations']=2
        with self.g.files.lock():
            with self.assertRaises(Rejected):self.g.set_operator(value)
    def test_invalid_operator_cap_rejected(self):
        value=copy.deepcopy(self.g.operator());value['caps']['max_synthesis_calls_per_wp']=0
        with self.assertRaises(Rejected):validate_operator(value)

if __name__=='__main__':unittest.main()
