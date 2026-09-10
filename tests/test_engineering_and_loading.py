import copy,io,sys,unittest
from contextlib import redirect_stdout
from support import *
from common import encode,parse,contained
from packets import hydrate
sys.path.insert(0,str(ROOT/'evaluation'))
from usage_summary import summarize
from context_footprint import measure

class EngineeringAndIntegrity(Base):
    def engineering_plan(self):
        def change(r):
            w=r['plan']['work_packages'][0];w['owner_role']='engineering';w['scope']['paths']=['src'];w['required_checks']=['unit']
        self.g.apply_plan(self.proposal(change),self.view())
    def test_actual_worktree_engineering_candidate(self):
        self.engineering_plan();other=Path(self.tmp.name)/'engineering';git(self.repo,'worktree','add','-q','-b','engineering',str(other));b=self.launch(self.issue(),repo=other,workspace='local/engineering');(other/'src/main.py').write_text('VALUE = 2\n');c=self.candidate(b=b);self.g.r0(c);self.review(c);self.g.accept('WP1',self.view());self.assertEqual((self.repo/'src/main.py').read_text(),'VALUE = 1\n')
    def test_reviewer_pristine_worktree_rejected(self):
        self.engineering_plan();other=Path(self.tmp.name)/'candidate';git(self.repo,'worktree','add','-q','-b','candidate',str(other));b=self.launch(self.issue(),repo=other,workspace='local/candidate');(other/'src/main.py').write_text('VALUE = 2\n');c=self.candidate(b=b);self.g.r0(c)
        with self.assertRaises(Rejected):self.launch(self.issue('review_r1'),repo=self.repo,workspace='local/main')
    def test_owner_snapshot_manifest_preserved(self):
        c=self.candidate();self.assertIn('snapshot_manifest',self.g.files.get(c))
    def test_snapshot_uses_git_diff_identity_not_host_stat_modes(self):
        base=head(self.repo);(self.repo/'src/main.py').write_text('VALUE = 2\n');value=snapshot(self.repo,base,['src'])
        self.assertIn('worktree_diff_sha256',value['manifest'])
        self.assertTrue(all('mode' not in item for item in value['manifest']['files']))
    def test_snapshot_excludes_task_control_files_even_if_git_staged(self):
        base=head(self.repo);before=snapshot(self.repo,base,[])['sha256']
        noise=self.g.files.root/'debug.tmp';noise.write_text('transaction noise\n');git(self.repo,'add','-f','.task/debug.tmp')
        self.assertEqual(snapshot(self.repo,base,[])['sha256'],before)
    def test_unfinalized_snapshot_cannot_hide_changed_declared_evidence(self):
        self.engineering_plan();b=self.launch(self.issue());(self.repo/'raw.txt').write_text('Unauthorized alteration')
        with self.assertRaises(Rejected):self.candidate(b=b)
    def test_structural_tag_requires_r2(self):
        self.engineering_plan();b=self.launch(self.issue());r=self.result(b);r['structural_tags']=['architectural_refactor'];c=self.candidate(b=b,result=r);self.g.r0(c);self.review(c)
        with self.assertRaises(Rejected):self.g.accept('WP1',self.view())
        self.review(c,'review_r2');self.g.accept('WP1',self.view())
    def test_path_name_alone_does_not_require_r2(self):
        def change(r):
            w=r['plan']['work_packages'][0];w['owner_role']='engineering';w['scope']['paths']=['src','api'];w['required_checks']=['unit']
        self.g.apply_plan(self.proposal(change),self.view());b=self.launch(self.issue());(self.repo/'api').mkdir();(self.repo/'api/public.py').write_text('VALUE = 2\n')
        c=self.candidate(b=b);self.g.r0(c);self.review(c);self.g.accept('WP1',self.view())
        self.assertEqual(self.g.state()['accepted']['WP1']['review'],'r1')
    def test_retired_policy_structural_path_requires_explicit_migration(self):
        self.engineering_plan()
        with self.g.files.lock():
            s=self.g.state();legacy=self.g.files.get(s['policy_ref']);legacy['structural_paths']=['src'];s['policy_ref']=self.g.files.put('provenance','legacy-policy',legacy);self.g.files.commit(s)
        with self.assertRaises(Rejected) as caught:self.issue()
        self.assertEqual(caught.exception.code,'TASK_MIGRATION_REQUIRED')
    def test_policy_result_cannot_choose_checks(self):
        def change(r):r['plan']['work_packages'][0]['required_checks']=['unapproved-shell']
        with self.assertRaises(Rejected):self.proposal(change)
        self.assertEqual(len(self.g.files.all('planner_rejections')),1)
    def test_failed_domain_check_blocks(self):
        self.engineering_plan()
        # This test constructs a separate operator-pinned policy/project, not an in-flight policy edit.
        from verification import run_checks
        checks=run_checks(self.repo,['bad'],{'bad':{'argv':[sys.executable,'-c','raise SystemExit(1)'],'timeout_seconds':5}});self.assertFalse(checks[0]['passed'])
    def test_check_that_changes_candidate_rejected(self):
        self.engineering_plan();b=self.launch(self.issue());c=self.candidate(b=b)
        # Use a distinct test-only approved catalog to exercise the R0 mutation detector.
        original=self.g.policy
        def test_policy(s=None):
            p=original(s);p['checks']['unit']={'argv':[sys.executable,'-c',"from pathlib import Path;Path('src/main.py').write_text('VALUE = 99')"],'timeout_seconds':5};return p
        self.g.policy=test_policy
        with self.assertRaises(Rejected):self.g.r0(c)
    def test_evidence_symlink_forbidden(self):
        (self.repo/'alias.txt').symlink_to(self.repo/'raw.txt')
        from verification import verify_evidence
        with self.assertRaises(Rejected):verify_evidence(self.repo,[{'path':'alias.txt','sha256':file_hash(self.repo/'raw.txt'),'version':'1'}],[])

    def test_evidence_manifest_keeps_candidate_compact_and_recursively_verified(self):
        import contextlib,dispatchctl
        from verification import verify_evidence
        self.engineering_plan();packet=self.issue();binding=self.launch(packet)
        evidence_dir=self.repo/'src/evidence';evidence_dir.mkdir();(evidence_dir/'run.log').write_text('pass\n');(evidence_dir/'metrics.yaml').write_text('loss: 0\n')
        manifest=evidence_dir/'evidence.mats.yaml';out=io.StringIO()
        with contextlib.redirect_stdout(out):
            rc=dispatchctl.main(['--repo',str(self.repo),'evidence',self.g.files.get(packet)['id'],str(manifest),str(evidence_dir)])
        self.assertEqual(rc,0);generated=parse(out.getvalue().encode());self.assertEqual(generated['entry_count'],2)
        result=self.result(binding);result.pop('snapshot');result['evidence']=generated['evidence']
        prepared=self.g.prepare_delivery(packet,result,workspace=self.repo)
        self.assertEqual(len(prepared['evidence']),1);self.assertTrue(prepared['evidence'][0]['version'].startswith('manifest@'))
        self.assertTrue(self.g.check_delivery(packet,prepared)['valid'])
        candidate=self.g.import_result(binding,prepared,self.done(binding));self.g.r0(candidate)
        review_packet=self.g.files.get(self.issue('review_r1'))
        self.assertEqual(review_packet['candidate']['evidence_paths'],['src/evidence/metrics.yaml','src/evidence/run.log'])
        for key in ('snapshot_manifest','completion','binding_ref','evidence'):self.assertNotIn(key,review_packet['candidate'])
        (evidence_dir/'run.log').write_text('changed\n')
        with self.assertRaisesRegex(Rejected,'stale manifest evidence'):
            verify_evidence(self.repo,prepared['evidence'],[],workspace_snapshot=prepared['snapshot'])

    def test_evidence_alias_derives_packet_digest_and_workspace(self):
        import contextlib,dispatchctl
        self.engineering_plan();packet=self.issue();self.launch(packet)
        evidence_dir=self.repo/'src/evidence-short';evidence_dir.mkdir();(evidence_dir/'run.log').write_text('pass\n')
        manifest=evidence_dir/'evidence.mats.yaml';out=io.StringIO()
        with contextlib.redirect_stdout(out):
            rc=dispatchctl.main(['--repo',str(self.repo),'evidence',self.g.files.get(packet)['id'],str(manifest),str(evidence_dir)])
        self.assertEqual(rc,0);generated=parse(out.getvalue().encode());self.assertEqual(generated['entry_count'],1)
    def test_evidence_bundle_output_requires_a_yaml_suffix(self):
        import contextlib,dispatchctl
        self.engineering_plan();packet=self.issue();self.launch(packet)
        evidence_dir=self.repo/'src/evidence-suffix';evidence_dir.mkdir();(evidence_dir/'run.log').write_text('pass\n')
        err=io.StringIO()
        with contextlib.redirect_stderr(err):
            rc=dispatchctl.main(['--repo',str(self.repo),'evidence',self.g.files.get(packet)['id'],
                                 str(evidence_dir/'evidence.sha256'),str(evidence_dir/'run.log')])
        self.assertEqual(rc,2);self.assertIn('ordinary .sha256 files use an evidence',err.getvalue())
    def test_scope_external_read_only_log_is_automatically_pinned(self):
        self.engineering_plan();packet=self.issue();binding=self.launch(packet);result=self.result(binding);result.pop('snapshot')
        log=self.repo/'Moonlight-new.log';log.write_text('decoder observation\n');result['evidence'].append(log.name)
        prepared=self.g.prepare_delivery(packet,result,workspace=self.repo)
        self.assertTrue(self.g.check_delivery(packet,prepared)['valid'])
        candidate=self.g.import_result(binding,prepared,self.done(binding));stored=self.g.files.get(candidate)
        self.assertEqual(stored['snapshot_manifest']['declared_read_evidence'][0]['path'],log.name)
        self.assertNotIn(log.name,[item['path'] for item in stored['snapshot_manifest']['files']])
        self.g.r0(candidate);self.review(candidate)
    def test_unrelated_untracked_file_does_not_interrupt_delivery(self):
        self.engineering_plan();packet=self.issue();binding=self.launch(packet);result=self.result(binding);result.pop('snapshot')
        extra=self.repo/'user-drop.log';extra.write_text('new external input\n')
        prepared=self.g.prepare_delivery(packet,result,workspace=self.repo)
        self.assertTrue(self.g.check_delivery(packet,prepared)['valid'])
        candidate=self.g.import_result(binding,prepared,self.done(binding));live=self.g.verify_candidate(self.g.files.get(candidate))
        self.assertNotIn(extra.name,[item['path'] for item in live['manifest']['files']])
    def test_unrelated_tracked_change_does_not_interrupt_delivery(self):
        self.engineering_plan();packet=self.issue();binding=self.launch(packet);result=self.result(binding);result.pop('snapshot')
        (self.repo/'raw.txt').write_text('user-updated input\n')
        result['evidence']=[]
        prepared=self.g.prepare_delivery(packet,result,workspace=self.repo)
        self.assertTrue(self.g.check_delivery(packet,prepared)['valid'])
        candidate=self.g.import_result(binding,prepared,self.done(binding));live=self.g.verify_candidate(self.g.files.get(candidate))
        self.assertNotIn('raw.txt',[item['path'] for item in live['manifest']['files']])
    def test_stale_packet_scope_ref_is_advice_not_candidate_gate(self):
        self.engineering_plan()
        def add_seed(r):r['plan']['work_packages'][0]['scope']['refs']=[self.evidence()[0]]
        self.g.apply_plan(self.proposal(add_seed),self.view())
        packet=self.issue();binding=self.launch(packet);result=self.result(binding);result.pop('snapshot');result['evidence']=[]
        (self.repo/'raw.txt').write_text('new user-supplied contents\n')
        prepared=self.g.prepare_delivery(packet,result,workspace=self.repo)
        self.assertTrue(self.g.check_delivery(packet,prepared)['valid'])
    def test_automatically_pinned_read_evidence_is_stable(self):
        self.engineering_plan();packet=self.issue();binding=self.launch(packet);result=self.result(binding);result.pop('snapshot')
        log=self.repo/'Moonlight-new.log';log.write_text('first\n');result['evidence'].append(log.name)
        prepared=self.g.prepare_delivery(packet,result,workspace=self.repo);log.write_text('second\n')
        with self.assertRaisesRegex(Rejected,'snapshot does not match'):
            self.g.check_delivery(packet,prepared)
    def test_finalizer_rerun_refreshes_its_own_stale_read_pin(self):
        self.engineering_plan();packet=self.issue();binding=self.launch(packet);result=self.result(binding);result.pop('snapshot')
        log=self.repo/'debug.log';log.write_text('first\n');result['evidence'].append(log.name)
        first=self.g.prepare_delivery(packet,result,workspace=self.repo);old=first['evidence'][-1]['sha256']
        log.write_text('second\n');second=self.g.prepare_delivery(packet,first,workspace=self.repo)
        self.assertNotEqual(second['evidence'][-1]['sha256'],old)
        self.assertTrue(self.g.check_delivery(packet,second)['valid'])
    def test_control_read_grant_command_is_removed(self):
        import contextlib,dispatchctl
        out=io.StringIO()
        with contextlib.redirect_stdout(out),self.assertRaises(SystemExit):dispatchctl.main(['-h'])
        self.assertNotIn('allow-read-evidence',out.getvalue())
    def test_payload_record_collision(self):
        self.g.files.put('payloads','test',{'a':1})
        with self.assertRaises(Rejected):self.g.files.put('payloads','test',{'a':2})
    def test_policy_tamper_detected(self):
        ref=self.g.state()['policy_ref'];p=self.g.files.root/ref['path'];p.write_text('changed: true')
        with self.assertRaises(Rejected):self.issue()
    def test_semantic_store_has_no_snapshot_db(self):
        self.candidate();names={p.name for p in self.g.files.root.iterdir()};self.assertIn('semantic.yaml',names);self.assertTrue({'snapshots','objects','current.yaml','outbox'} .isdisjoint(names))
    def test_coordinator_uses_one_os_released_mutex_file(self):
        with self.g.files.lock():pass
        self.assertEqual([p.name for p in self.g.files.root.glob('*.lock')],['coordinator.lock'])
    def test_reinitialization_rejected(self):
        with self.assertRaises(Rejected):self.g.initialize(self.p,self.pl,'RUN',policy=self.policy,simulation=True)
    def test_new_initial_plan_requires_milestone_id(self):
        other=Path(self.tmp.name)/'bad-plan';other.mkdir();git(other,'init','-q');git(other,'config','user.email','test@example.invalid');git(other,'config','user.name','Conformance Test');(other/'x').write_text('x');git(other,'add','.');git(other,'commit','-qm','baseline')
        bad=copy.deepcopy(self.pl);bad['plan_id']='project-plan'
        with self.assertRaisesRegex(Rejected,'milestone staging ID'):Guards(other).initialize(self.p,bad,'RUN',policy=self.policy,simulation=True)
    def test_provider_freshness_not_a_security_capability(self):
        # Fixture remains explicitly simulation; cannot import it into a production-marked project.
        r=self.g.files.get(self.g.state()['control_ref']);r['simulation']=False
        with self.assertRaises(Rejected):self.g.attach_control(r)
    def test_cli_doctor_makes_no_live_claim(self):
        import dispatchctl
        out=io.StringIO()
        with redirect_stdout(out):rc=dispatchctl.main(['doctor'])
        self.assertEqual(rc,0);v=parse(out.getvalue().encode());self.assertEqual(v['version'],'1.0.0');self.assertFalse(v['live_orca_verified']);self.assertEqual(v['model_calls'],0)
    def test_worker_packet_no_root_no_eager_full_schema(self):
        p=hydrate(self.g.files,self.issue());self.assertNotIn('output_schema',p);self.assertIn('schema_on_demand',p);self.assertNotIn('# Multi-Agent Task Split v17',encode(p).decode())

    def test_local_evidence_steer_does_not_route_to_planner_or_user_question(self):
        routing=(ROOT/'skill/multi-agent-task-split/references/routing.md').read_text(encoding='utf-8')
        workflow=(ROOT/'skill/multi-agent-task-split/references/workflow.md').read_text(encoding='utf-8')
        planner=(ROOT/'skill/multi-agent-task-split/references/roles/planner.md').read_text(encoding='utf-8')
        self.assertIn('an exhaustive allowlist',routing)
        self.assertIn('never read permissions',routing)
        self.assertIn('No read grant, plan/version change or new packet exists',routing)
        self.assertIn('Do not edit `scope.refs`, invoke Planner, or apply an already-issued proposal merely to attach/read evidence',routing)
        self.assertIn('Resolve MATS schema/ref/hash/snapshot/runtime/routing/retry/session mechanics locally',workflow)
        self.assertIn('close its exchange without applying the proposal',workflow)
        self.assertIn('Read paths are advisory and need no Control grant',workflow)
        self.assertIn('Never ask about schema, refs, hashes, runtime',planner)

class FootprintAndUsage(unittest.TestCase):
    def test_root_skill_stays_within_explicit_four_kib_budget(self):self.assertLessEqual((ROOT/'skill/multi-agent-task-split/SKILL.md').stat().st_size,4096)
    def test_description_small(self):
        s=(ROOT/'skill/multi-agent-task-split/SKILL.md').read_text();meta=parse(s.split('---',2)[1].encode());self.assertLessEqual(len(meta['description']),150)
    def test_roles_small(self):
        # Stable Identity/Owns/May/Must-not/Output/Handoff/Refresh recaps are worth
        # a modest budget because they prevent drift across long sessions. Control
        # may use slightly more because it coordinates but does no domain execution.
        for f in (ROOT/'skill/multi-agent-task-split/references/roles').glob('*.md'):
            self.assertLessEqual(f.stat().st_size,1536 if f.name=='control.md' else 1250,f.name)
    def test_no_implicit_invocation(self):self.assertIs(load(ROOT/'skill/multi-agent-task-split/agents/openai.yaml')['policy']['allow_implicit_invocation'],False)
    def test_no_runtime_kernel_or_lease_policy(self):
        sk=ROOT/'skill/multi-agent-task-split';self.assertFalse((sk/'scripts/kernel.py').exists());p=load(sk/'config/policy.yaml');self.assertNotIn('lease_seconds',encode(p).decode());self.assertNotIn('capability_ttl',encode(p).decode())
    def row(self):return {'dispatch_id':'D1','model':'gpt-5.6-terra','input_tokens':100,'output_tokens':50,'reasoning_tokens':40,'cost_microusd':800,'complete_native_loop':True}
    def test_reasoning_not_double_counted(self):self.assertEqual(summarize([self.row()])['known_complete_tokens'],150)
    def test_unknown_usage_not_zero_project_total(self):
        r=self.row();r['cost_microusd']=None;out=summarize([r]);self.assertFalse(out['project_total_known']);self.assertEqual(out['unknown_or_partial_dispatches'],['D1'])
    def test_partial_loop_not_complete_usage(self):
        r=self.row();r['complete_native_loop']=False;self.assertEqual(summarize([r])['complete_usage_dispatches'],0)
    def test_usage_deduplicated(self):r=self.row();self.assertEqual(summarize([r,r])['dispatches_observed'],1)
    def test_conflicting_cumulative_usage_rejected(self):
        r=self.row();r2=copy.deepcopy(r);r2['output_tokens']=200
        with self.assertRaises(Rejected):summarize([r,r2])
    def test_reasoning_exceeding_output_rejected(self):
        r=self.row();r['reasoning_tokens']=60
        with self.assertRaises(Rejected):summarize([r])
    def test_no_observations_no_cost_claim(self):self.assertFalse(summarize([])['project_total_known'])
    def test_managed_cost_includes_control_and_attributes_orca_without_double_counting(self):
        worker=self.row();control={'session_id':'CONTROL1','model':'gpt-5.6-luna','input_tokens':35000,'output_tokens':1000,'reasoning_tokens':800,'cost_microusd':2000,'complete_control_session':True,
            'context_loads':[{'load_id':'M1','component':'mats:activation-and-state','input_tokens':26000,'complete':True,'included_in_control_input':True},
                             {'load_id':'O1','component':'orca:orchestration','input_tokens':9000,'complete':True,'included_in_control_input':True}]}
        out=summarize({'dispatches':[worker],'control_sessions':[control]})
        self.assertEqual(out['known_complete_tokens'],36150);self.assertEqual(out['known_complete_control_tokens'],36000)
        self.assertEqual(out['known_attributed_context_input_tokens'],35000);self.assertFalse(out['context_tokens_added_again'])
        self.assertEqual(out['known_complete_cost_microusd'],2800);self.assertTrue(out['project_total_known'])
    def test_managed_cost_is_unknown_when_control_or_orca_context_is_omitted(self):
        control={'session_id':'CONTROL1','model':'gpt-5.6-luna','input_tokens':100,'output_tokens':10,'reasoning_tokens':5,'cost_microusd':20,'complete_control_session':True,
                 'context_loads':[{'load_id':'M1','component':'mats:activation','input_tokens':80,'complete':True,'included_in_control_input':True}]}
        out=summarize({'dispatches':[],'control_sessions':[control]})
        self.assertFalse(out['project_total_known']);self.assertEqual(out['missing_or_incomplete_control_context'],['CONTROL1'])
    def test_static_context_footprint_includes_observed_orca_entrypoints(self):
        mats=ROOT/'skill/multi-agent-task-split';orca=ROOT/'tests/support.py';out=measure(mats,{'test-orca':orca},1234)
        expected=sum((mats/path).stat().st_size for path in ('SKILL.md','references/roles/control.md','references/workflow.md','references/routing.md'))
        self.assertEqual(out['mats_activation']['total'],expected)
        self.assertEqual(out['orca_skill_entrypoints']['total'],orca.stat().st_size)
        self.assertEqual(out['normal_after_first_state_with_observed_orca'],expected+(mats/'references/storage.md').stat().st_size+orca.stat().st_size)
        self.assertEqual(out['native_anomaly_with_observed_orca'],out['normal_after_first_state_with_observed_orca']+(mats/'references/native-boundary.md').stat().st_size+1234)

if __name__=='__main__':unittest.main()
