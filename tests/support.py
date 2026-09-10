import copy,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'skill/multi-agent-task-split/scripts'))
from common import Rejected,digest,load
from guards import Guards
from verification import git,head,snapshot,file_hash
from contracts import contract_digest
from routing import fixed_binding


def memo():return {'claims':['Measured semantics match the contract.'],'observations':['Inspected raw source.'],'unknowns':[],'downstream_impact':[],'decision_requested':'','evidence_refs':[]}
def project():return {'schema_version':9,'project_id':'P','goal':'Build a verified tool','phase':'research','commitments':[{'id':'C1','statement':'Evidence precedes commitment.','scope':'global','applies_to':[]}],'boundaries':['No production deployment.'],'strategic_risks':['Silent semantic error'],'working_hypotheses':[],'open_questions':[]}
def wp(wid='WP1',role='research',deps=None):return {'id':wid,'title':'Understand behavior','owner_role':role,'objective':'Establish behavior with evidence','constraints':[],'exit_conditions':['Raw evidence supports the result.'],'dependencies':deps or [],'required_skills':[],'scope':{'paths':['src'] if role=='engineering' else [],'refs':[]},'impact':'local','review_policy':'r1','required_checks':['unit'] if role=='engineering' else [],'depends_on_commitments':[]}
def plan():return {'schema_version':9,'plan_id':'m0_baseline','project_id':'P','version':1,'work_packages':[wp(),wp('WP2',deps=['WP1']),wp('WP3')]}

class Base(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.repo=Path(self.tmp.name)/'repo';self.repo.mkdir();self.seq=0
        git(self.repo,'init','-q');git(self.repo,'config','user.email','test@example.invalid');git(self.repo,'config','user.name','Conformance Test')
        (self.repo/'.gitignore').write_text('.task/\n__pycache__/\n');(self.repo/'raw.txt').write_text('Source observations\n');(self.repo/'src').mkdir();(self.repo/'src/main.py').write_text('VALUE = 1\n')
        git(self.repo,'add','.');git(self.repo,'commit','-qm','baseline')
        self.p=project();self.pl=plan();self.policy=load(ROOT/'skill/multi-agent-task-split/config/policy.yaml');self.policy['checks']={'unit':{'argv':[sys.executable,'-c','assert 1+1==2'],'timeout_seconds':10}}
        self.g=Guards(self.repo);self.g.initialize(self.p,self.pl,'RUN',policy=self.policy,simulation=True)
        control={'schema_version':9,'run_id':'RUN','session_id':'SCONTROL','effective':fixed_binding(self.policy,'control'),'role_contract_digest':digest((ROOT/'skill/multi-agent-task-split/references/roles/control.md').read_text()),'source':'simulated root-session attestation','simulation':True}
        self.g.attach_control(control)
    def tearDown(self):self.tmp.cleanup()
    def uid(self,prefix='I'):self.seq+=1;return prefix+str(self.seq)
    def view(self,active=None,users=None):return {'project_id':'P','run_id':'RUN','complete':True,'source':'test-only full native view','simulation':True,'active_dispatches':active or [],'workspace_users':users or []}
    def evidence(self):return [{'path':'raw.txt','sha256':file_hash(self.repo/'raw.txt'),'version':head(self.repo)}]
    def issue(self,op='owner',wid='WP1',request=None):return self.g.issue(self.uid('PK'),op,wp_id=wid,request=request)
    def launch(self,packet,session=None,repo=None,workspace='local/main'):
        body=self.g.files.get(packet);role=body['role'];wid=body['wp_id'];w=next((w for w in self.g.state()['plan']['work_packages'] if w['id']==wid),None)
        receipt={'schema_version':9,'run_id':'RUN','task_id':self.uid('T'),'dispatch_id':self.uid('D'),'session_id':session or self.uid('S'),'workspace_key':workspace,'workspace_path':str(repo or self.repo),'access':'write' if w and w['scope']['paths'] and role in {'research','engineering'} else 'read_snapshot','fresh_context':session is None,'effective':fixed_binding(self.policy,role),'packet_digest':packet['sha256'],'source':'simulated native launch','simulation':True}
        return self.g.bind(packet,receipt)
    def done(self,b):
        r=self.g.files.get(b)['receipt'];return {k:r[k] for k in ('run_id','task_id','dispatch_id','session_id')}|{'outcome':'succeeded','worker_done_verified':True,'source':'simulated worker_done','simulation':True}
    def result(self,b,status='candidate'):
        binding=self.g.files.get(b);packet=self.g.files.get(binding['packet_ref']);w=next(w for w in self.g.state()['plan']['work_packages'] if w['id']==packet['wp_id'])
        return {'schema_version':9,'status':status,'summary':'Source-authored finding','evidence':self.evidence(),'unresolved':[],'impact':'local','structural_tags':[],'snapshot':snapshot(Path(binding['receipt']['workspace_path']),packet['base_commit'],w['scope']['paths'])['sha256'],'source_memo':memo(),'consumed_sides':[]}
    def candidate(self,wid='WP1',b=None,result=None):
        b=b or self.launch(self.issue(wid=wid));return self.g.import_result(b,result or self.result(b),self.done(b))
    def review(self,cref,role='review_r1',outcome='pass'):
        c=self.g.files.get(cref);owner=self.g.files.get(c['binding_ref'])['receipt'];b=self.launch(self.issue(role,c['wp_id']),repo=Path(owner['workspace_path']),workspace=owner['workspace_key']);r={'schema_version':9,'outcome':outcome,'target_digest':cref['sha256'],'summary':'Independently checked','findings':[],'source_memo':memo()}
        if outcome=='plan_conflict':r['source_memo']['decision_requested']='Revise an invalid commitment.'
        if role=='review_r1' and outcome=='needs_synthesis':self.side(b,'synthesis')
        return self.g.import_result(b,r,self.done(b))
    def accepted(self,wid='WP1'):
        c=self.candidate(wid);self.g.r0(c);self.review(c);self.g.accept(wid,self.view());return c
    def bootstrap_proposal(self,mutate=None):
        req={'reason':'bootstrap','question':'Frame coarse project and Work Packages','source_refs':[],'directive_ids':[],'affected_wp_ids':[]}
        b=self.launch(self.issue('planner',None,req));s=self.g.state();r={'schema_version':9,'mode':'full','base_plan_version':s['plan']['version'],'basis_refs':[],'project':copy.deepcopy(s['project']),'plan':copy.deepcopy(s['plan']),'invalidate_accepted':[],'reason':'Source-backed bootstrap design'};r['plan']['version']+=1
        if mutate:mutate(r)
        return self.g.import_result(b,r,self.done(b))
    def proposal(self,mutate=None,request=None):
        # Runtime planning is patch-only. Tests may express a desired target, then this helper
        # derives the sparse patch a Planner would return.
        s=self.g.state();target={'project':copy.deepcopy(s['project']),'plan':copy.deepcopy(s['plan']),'invalidate_accepted':[]}
        target['plan']['version']+=1
        if mutate: mutate(target)
        if request is None:
            uid=self.uid('U');self.g.directive({'id':uid,'raw_text':'Adjust the active project plan without changing model policy.','intent':'project_steer'})
            request={'reason':'project_steer','question':'Apply a scoped runtime plan adjustment','source_refs':[],'directive_ids':[uid],'affected_wp_ids':[]}
        b=self.launch(self.issue('planner',None,request))
        oldp,oldpl=s['project'],s['plan'];newp,newpl=target['project'],target['plan']
        set_fields={}
        for key in ('goal','phase','boundaries','strategic_risks','working_hypotheses','open_questions'):
            if oldp[key]!=newp[key]: set_fields[key]=copy.deepcopy(newp[key])
        oldc={x['id']:x for x in oldp['commitments']};newc={x['id']:x for x in newp['commitments']}
        cup=[copy.deepcopy(v) for k,v in newc.items() if oldc.get(k)!=v];crem=[k for k in oldc if k not in newc]
        oldw={x['id']:x for x in oldpl['work_packages']};neww={x['id']:x for x in newpl['work_packages']}
        wup=[copy.deepcopy(v) for k,v in neww.items() if oldw.get(k)!=v];wrem=[k for k in oldw if k not in neww]
        r={'schema_version':9,'mode':'patch','base_plan_version':oldpl['version'],'basis_refs':[],
           'project_patch':{'set':set_fields,'commitments':{'upsert':cup,'remove':crem}},
           'plan_patch':{'work_packages':{'upsert':wup,'remove':wrem}},
           'invalidate_accepted':copy.deepcopy(target['invalidate_accepted']),'reason':'Source-backed runtime adjustment'}
        return self.g.import_result(b,r,self.done(b))
    def patch_proposal(self,project_patch=None,plan_patch=None,*,affected=None):
        uid=self.uid('U');self.g.directive({'id':uid,'raw_text':'Adjust the active project plan without changing model policy.','intent':'project_steer'})
        req={'reason':'project_steer','question':'Apply a scoped runtime plan adjustment','source_refs':[],'directive_ids':[uid],'affected_wp_ids':affected or []}
        b=self.launch(self.issue('planner',None,req));s=self.g.state()
        r={'schema_version':9,'mode':'patch','base_plan_version':s['plan']['version'],'basis_refs':[],
           'project_patch':project_patch or {'set':{},'commitments':{'upsert':[],'remove':[]}},
           'plan_patch':plan_patch or {'work_packages':{'upsert':[],'remove':[]}},
           'invalidate_accepted':[],'reason':'Source-backed runtime adjustment'}
        return self.g.import_result(b,r,self.done(b))
    def side(self,source_binding,role='synthesis'):
        req={'schema_version':9,'kind':role,'class':'adjudication' if role=='synthesis' else 'bulk_index','question':'Which supported explanation fits?','current_findings':['Observations differ.'],'competing_explanations':['A','B'],'attempted':['Inspected the decisive paths.'],'evidence':self.evidence(),'affected_commitments':[],'requested_output':'Bounded decision with evidence','verification_plan':'Owner checks decisive raw records.','benefit':'Avoid re-reading the entire corpus.','decision_key':'SEMANTICS'}
        return self.g.side_request(source_binding,req,caller_session=self.g.files.get(source_binding)['receipt']['session_id'])
    def side_result(self,b):
        r={'schema_version':9,'status':'done','summary':'Bounded source advice','evidence':self.evidence(),'unknowns':[],'coverage':{'examined':1,'total':1,'excluded':[]},'proposed_next_actions':['Check the decisive observation.']}
        return self.g.import_result(b,r,self.done(b))
