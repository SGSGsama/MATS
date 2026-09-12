"""Readable semantic document + named immutable artifacts. No long-lived event/snapshot DB."""
from __future__ import annotations
import os, re
from contextlib import contextmanager
from pathlib import Path
from common import Rejected, atomic_write, contained, digest, encode, identifier, load, logical_relative
from contracts import validate

MILESTONE_ID=re.compile(r'm(0|[1-9][0-9]{0,5})(?:_[A-Za-z0-9][A-Za-z0-9.-]{0,80})?')
MILESTONE_FOLDERS=frozenset({'packets','bindings','results','r0','reviews','requests','planner_rejections','planner_rejected_payloads'})

def milestone_id(value):
    if not MILESTONE_ID.fullmatch(value or ''):
        raise Rejected('milestone staging ID must be m<number> or m<number>_<milestone-slug>')
    return value

if os.name == 'nt':
    import msvcrt
else:
    import fcntl

class Records:
    def __init__(self,repo):
        self.repo=Path(repo).resolve()
        self.root=contained(self.repo,'.task')
        self.root.mkdir(parents=True,exist_ok=True)

    @contextmanager
    def lock(self):
        """One OS-released coordinator mutex; its persistent file is not lock state."""
        p=contained(self.root,'coordinator.lock')
        if p.is_symlink(): raise Rejected('refusing symlink lock target')
        fd=os.open(p,os.O_CREAT|os.O_RDWR,0o600)
        acquired=False
        try:
            if os.name == 'nt':
                # msvcrt.locking locks bytes from the current offset. Ensure byte 0 exists.
                if os.fstat(fd).st_size < 1:
                    os.write(fd,b'\0'); os.fsync(fd)
                os.lseek(fd,0,os.SEEK_SET)
                try: msvcrt.locking(fd,msvcrt.LK_NBLCK,1)
                except OSError as e: raise Rejected('another local coordinator action is committing') from e
            else:
                try: fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
                except BlockingIOError as e: raise Rejected('another local coordinator action is committing') from e
            acquired=True
            yield
        finally:
            try:
                if acquired and os.name == 'nt':
                    os.lseek(fd,0,os.SEEK_SET); msvcrt.locking(fd,msvcrt.LK_UNLCK,1)
                elif acquired: fcntl.flock(fd,fcntl.LOCK_UN)
            finally: os.close(fd)

    def control_path(self, value, *, prefixes=()):
        """Resolve a control-plane path and require it to live under .task.

        Relative values are interpreted relative to .task, not repository root. The path
        may keep any useful file layout (e.g. bootstrap/X/project.yaml + plan.yaml); only
        its control-plane root is fixed.
        """
        p=Path(value)
        if not p.is_absolute():
            parts=p.parts
            if parts and parts[0] == '.task': parts=parts[1:]
            p=self.root.joinpath(*parts)
        try: logical=logical_relative(self.root,p)
        except Rejected: raise Rejected('control-plane files must live under .task')
        parts=logical.split('/')
        direct=lambda prefix: logical==prefix or logical.startswith(prefix+'/')
        nested=lambda prefix: len(parts)>=3 and MILESTONE_ID.fullmatch(parts[0]) and parts[1]==prefix
        if prefixes and not any(direct(x.rstrip('/')) or nested(x.rstrip('/')) for x in prefixes):
            raise Rejected('control-plane file is outside allowed .task subdirectory')
        return contained(self.root,logical)

    def load_control(self,value,*,prefixes=()):
        p=self.control_path(value,prefixes=prefixes)
        return load(p)

    def milestone_dir(self,name):
        milestone_id(name)
        p=contained(self.root,f'tmp/{name}')
        p.mkdir(parents=True,exist_ok=True)
        return p

    def ensure_milestone(self,name):
        """Create only the canonical milestone namespace selected by semantics."""
        p=contained(self.root,milestone_id(name))
        p.mkdir(exist_ok=True)
        return p

    def delivery_path(self,packet_id,*,create=False):
        identifier(packet_id)
        p=contained(self.root,f'tmp/deliveries/{packet_id}.yaml')
        if create:p.parent.mkdir(parents=True,exist_ok=True)
        return p

    def completion_event_path(self,dispatch_id,*,create=False):
        """Fixed script-owned staging for one normalized worker_done event."""
        identifier(dispatch_id)
        p=contained(self.root,f'tmp/completions/{dispatch_id}.yaml')
        if create:p.parent.mkdir(parents=True,exist_ok=True)
        return p

    def lifecycle_operation_path(self,kind,native_id,*,create=False):
        """Durable script-only proof that one native lifecycle step completed."""
        identifier(kind);identifier(native_id)
        if kind not in {'release','ack'}:raise Rejected('invalid lifecycle operation kind')
        p=contained(self.root,f'operations/{kind}-{native_id}.yaml')
        if create:p.parent.mkdir(parents=True,exist_ok=True)
        return p

    def side_request_form_path(self,dispatch_id,operation,*,create=False):
        identifier(dispatch_id);identifier(operation)
        if operation not in {'luna_aux','synthesis'}:raise Rejected('invalid side request form operation')
        p=contained(self.root,f'tmp/side-requests/{dispatch_id}-{operation}.tsv')
        if create:p.parent.mkdir(parents=True,exist_ok=True)
        return p

    def planning_request_form_path(self,*,create=False):
        p=contained(self.root,'tmp/planning-request.tsv')
        if create:p.parent.mkdir(parents=True,exist_ok=True)
        return p

    def owner_query_path(self,query_id,*,create=False):
        identifier(query_id)
        p=contained(self.root,f'tmp/owner-queries/{query_id}.yaml')
        if create:p.parent.mkdir(parents=True,exist_ok=True)
        return p

    def owner_answer_path(self,query_id,*,create=False):
        identifier(query_id)
        p=contained(self.root,f'tmp/owner-answers/{query_id}.txt')
        if create:p.parent.mkdir(parents=True,exist_ok=True)
        return p

    def clear_owner_queries_for_delivery(self,delivery_id):
        """Clear answer-only tmp state after the shared native batch is acked."""
        identifier(delivery_id);root=contained(self.root,'tmp/owner-queries')
        if not root.exists():return []
        cleared=[]
        for path in sorted(root.glob('*.yaml')):
            value=load(path)
            if isinstance(value,dict) and value.get('kind')=='owner_query' and value.get('received_delivery_id')==delivery_id:
                query_id=value.get('id');identifier(query_id)
                path.unlink(missing_ok=True);self.owner_answer_path(query_id).unlink(missing_ok=True);cleared.append(query_id)
        return cleared

    def active_milestone(self):
        state_path=contained(self.root,'semantic.yaml')
        if not state_path.exists(): raise Rejected('semantic state does not define an active milestone')
        value=load(state_path)['plan']['plan_id']
        return milestone_id(value)

    def is_folder_path(self,logical,folder):
        parts=logical.split('/')
        return len(parts)>=3 and MILESTONE_ID.fullmatch(parts[0]) and parts[1]==folder

    def _artifact_path(self,folder,name):
        prefix=f'{self.active_milestone()}/' if folder in MILESTONE_FOLDERS else ''
        return contained(self.root,f'{prefix}{folder}/{name}.yaml')

    def next_index(self,folder,prefix='p'):
        identifier(folder);identifier(prefix)
        pat=re.compile(re.escape(prefix)+r'([0-9]{6})')
        values=[int(m.group(1)) for ref,_ in self.all(folder) if (m:=pat.fullmatch(Path(ref['path']).stem))]
        return f'{prefix}{(max(values,default=0)+1):06d}'

    def read(self): return load(contained(self.root,'semantic.yaml'))
    def read_operator(self): return load(contained(self.root,'operator.yaml'))
    def write_operator(self,value):
        validate('operator_control', value)
        atomic_write(contained(self.root,'operator.yaml'),encode(value))
    def commit(self,state):
        data=encode(state)
        if len(data)>4*1024*1024: raise Rejected('semantic document exceeds 4 MiB; archive a project boundary')
        atomic_write(contained(self.root,'semantic.yaml'),data)
    def put(self,folder,name,value):
        identifier(folder);identifier(name)
        data=encode(value)
        if folder in MILESTONE_FOLDERS:
            old=self.named(folder,name)
            if old:
                if encode(self.get(old))==data:return old
                raise Rejected('immutable artifact ID collision across milestones: '+name)
        p=self._artifact_path(folder,name)
        try: atomic_write(p,data,immutable=True)
        except FileExistsError:
            if p.read_bytes()!=data: raise Rejected('immutable artifact ID collision: '+str(p))
        return {'path':logical_relative(self.root,p), 'sha256':digest(value)}
    def get(self,ref):
        validate('internal_ref',ref)
        parts=ref['path'].split('/')
        if parts and parts[0] in MILESTONE_FOLDERS:
            raise Rejected('legacy top-level task artifact requires explicit migration; stop and report it to Control',code='TASK_MIGRATION_REQUIRED')
        value=load(contained(self.root,ref['path']))
        if digest(value)!=ref['sha256']: raise Rejected('artifact content changed: '+ref['path'])
        return value
    def named(self,folder,name):
        identifier(folder);identifier(name)
        paths=[self.root/folder/f'{name}.yaml'] if folder not in MILESTONE_FOLDERS else []
        if folder in MILESTONE_FOLDERS:
            for d in self.root.glob('m*'):
                if d.is_symlink(): raise Rejected('symlink in milestone artifact directory')
                if d.is_dir() and MILESTONE_ID.fullmatch(d.name):paths.append(d/folder/f'{name}.yaml')
        found=[p for p in paths if p.exists()]
        if not found:return None
        if len(found)>1:raise Rejected('ambiguous artifact ID across milestones; use its exact path')
        p=found[0]
        value=load(p)
        return {'path':logical_relative(self.root,p),'sha256':digest(value)}
    def all(self,folder):
        identifier(folder)
        roots=[self.root/folder] if folder not in MILESTONE_FOLDERS else []
        if folder in MILESTONE_FOLDERS:
            for d in self.root.glob('m*'):
                if d.is_symlink(): raise Rejected('symlink in milestone artifact directory')
                if d.is_dir() and MILESTONE_ID.fullmatch(d.name):roots.append(d/folder)
        paths=sorted(p for root in roots if root.exists() for p in root.glob('*.yaml'))
        if any(p.is_symlink() for p in paths): raise Rejected('symlink in semantic artifact directory')
        out=[]
        for p in paths:
            value=load(p)
            out.append(({'path':logical_relative(self.root,p),'sha256':digest(value)},value))
        return out
