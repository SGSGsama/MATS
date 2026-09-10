#!/usr/bin/env python3
"""Offline native-receipt simulation with a real Git worktree and real domain check."""
import sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'skill/multi-agent-task-split/scripts'))
from guards import Guards
from common import load,digest,encode
from routing import fixed_binding
from verification import git,head,snapshot,file_hash

def main():
    with tempfile.TemporaryDirectory() as td:
        repo=Path(td)/'main';repo.mkdir();git(repo,'init','-q');git(repo,'config','user.email','demo@example.invalid');git(repo,'config','user.name','Offline Demo')
        (repo/'.gitignore').write_text('.task/\n__pycache__/\n');(repo/'src').mkdir();(repo/'src/main.py').write_text('def double(x):\n    return x\n');(repo/'evidence.txt').write_text('Requirement: double(5) must be 10.\n');git(repo,'add','.');git(repo,'commit','-qm','baseline')
        project={'schema_version':9,'project_id':'DEMO','goal':'Implement and verify doubling','phase':'engineering','commitments':[{'id':'C1','statement':'double(5) is 10','scope':'global','applies_to':[]}],'boundaries':['No deployment'],'strategic_risks':[],'working_hypotheses':[],'open_questions':[]}
        wp={'id':'WP1','title':'Implement doubling','owner_role':'engineering','specialty':'python-implementer','objective':'Correct doubling','constraints':[],'exit_conditions':['double(5) equals 10'],'dependencies':[],'required_skills':[],'scope':{'paths':['src'],'refs':[]},'impact':'local','review_policy':'r1','required_checks':['double-test'],'depends_on_commitments':[]}
        plan={'schema_version':9,'plan_id':'m0_smoke','project_id':'DEMO','version':1,'work_packages':[wp]}
        policy=load(ROOT/'skill/multi-agent-task-split/config/policy.yaml');policy['checks']={'double-test':{'argv':[sys.executable,'-c',"import runpy; assert runpy.run_path('src/main.py')['double'](5)==10"],'timeout_seconds':10}}
        g=Guards(repo);g.initialize(project,plan,'RUN',policy=policy,simulation=True)
        g.attach_control({'schema_version':9,'run_id':'RUN','session_id':'CONTROL','effective':fixed_binding(policy,'control'),'role_contract_digest':digest((ROOT/'skill/multi-agent-task-split/references/roles/control.md').read_text()),'source':'offline simulated root identity','simulation':True})
        work=Path(td)/'owner';git(repo,'worktree','add','-q','-b','owner',str(work))
        view={'project_id':'DEMO','run_id':'RUN','complete':True,'source':'offline simulated runtime view','simulation':True,'active_dispatches':[],'workspace_users':[]}
        def bind(ref,role,label):
            return g.bind(ref,{'schema_version':9,'run_id':'RUN','task_id':'T'+label,'dispatch_id':'D'+label,'session_id':'S'+label,'workspace_key':'local/owner','workspace_path':str(work),'access':'write' if role=='engineering' else 'read_snapshot','fresh_context':True,'effective':fixed_binding(policy,role),'packet_digest':ref['sha256'],'source':'offline simulated native launch','simulation':True})
        def completion(b):
            r=g.files.get(b)['receipt'];return {k:r[k] for k in ('run_id','task_id','dispatch_id','session_id')}|{'outcome':'succeeded','worker_done_verified':True,'source':'offline simulated worker_done','simulation':True}
        ref=g.issue('OWNER','owner',wp_id='WP1');g.preflight(ref,view,'local/owner','write');owner=bind(ref,'engineering','OWNER')
        (work/'src/main.py').write_text('def double(x):\n    return x * 2\n')
        memo={'claims':['Implementation doubles its input.'],'observations':['The approved test passes for 5.'],'unknowns':[],'downstream_impact':[],'decision_requested':'','evidence_refs':[]}
        result={'schema_version':9,'status':'candidate','summary':'Fixed doubling','evidence':[{'path':'evidence.txt','sha256':file_hash(work/'evidence.txt'),'version':head(work)}],'unresolved':[],'impact':'local','structural_tags':[],'snapshot':snapshot(work,g.files.get(ref)['base_commit'],['src'])['sha256'],'source_memo':memo,'consumed_sides':[]}
        candidate=g.import_result(owner,result,completion(owner));r0=g.files.get(g.r0(candidate))
        review_ref=g.issue('REVIEW','review_r1',wp_id='WP1');reviewer=bind(review_ref,'review_r1','REVIEW')
        g.import_result(reviewer,{'schema_version':9,'outcome':'pass','target_digest':candidate['sha256'],'summary':'Simulated independent review; NOT model-quality evidence','findings':[],'source_memo':memo},completion(reviewer))
        accepted=g.accept('WP1',view)
        print(encode({'simulation':True,'real_git_worktree':True,'real_domain_check_passed':r0['passed'],'source_worktree_unchanged':'return x\n' in (repo/'src/main.py').read_text(),'accepted':bool(accepted),'model_calls':0,'live_orca_verified':False}).decode(),end='')
if __name__=='__main__':main()
