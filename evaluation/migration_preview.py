#!/usr/bin/env python3
"""Read-only schema-7 migration preview; never import runtime state or acceptance."""
import hashlib,sys,copy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'skill/multi-agent-task-split/scripts'))
from common import Rejected,load,parse,contained,identifier,encode

def preview(repo):
    root=contained(Path(repo).resolve(),'.task');pointer=load(contained(root,'current.yaml'));identifier(pointer['file']);data=contained(root,'snapshots/'+pointer['file']).read_bytes()
    if hashlib.sha256(data).hexdigest()!=pointer['sha256']:raise Rejected('v12 snapshot hash mismatch')
    s=parse(data)
    if s['schema_version']!=7:raise Rejected('expected v12 schema 7')
    project=copy.deepcopy(s['project']);plan=copy.deepcopy(s['plan']);project['schema_version']=8;plan['schema_version']=8
    project['commitments']=[{'id':f'C{i+1:03}','statement':text,'scope':'global','applies_to':[]} for i,text in enumerate(project['commitments'])]
    for w in plan['work_packages']:w['depends_on_commitments']=[]
    plan['version']=1
    return {'preview_only':True,'mutations':0,'requires_native_drain_and_new_directory':True,'project':project,'plan':plan,
            'legacy_done_requires_revalidation':[wid for wid,r in s['work_packages'].items() if r['status']=='done'],
            'accepted_imported':False,'note':'Commitments remain conservatively global until a source-backed Planner scopes them; attach new actual native/control receipts.'}
if __name__=='__main__':
    try:print(encode(preview(sys.argv[1])).decode(),end='')
    except (Rejected,OSError,KeyError,IndexError) as exc:print(str(exc),file=sys.stderr);raise SystemExit(2)
