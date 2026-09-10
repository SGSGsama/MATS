"""Deterministic source identity, Git scope and R0 check helpers."""
from __future__ import annotations
import hashlib
import os
import subprocess
from collections import Counter
from pathlib import Path
from common import Rejected, atomic_write, contained, digest, encode, relative, logical_from_parts, load, require_fields


def git(repo: Path, *args: str) -> bytes:
    try:
        cp=subprocess.run(["git","-C",str(repo),*args],capture_output=True,timeout=20,check=False)
    except (OSError,subprocess.TimeoutExpired) as exc:
        raise Rejected(f"Git unavailable/timed out: {exc}") from exc
    if cp.returncode: raise Rejected(cp.stderr.decode("utf-8",errors="replace").strip())
    return cp.stdout


def head(repo: Path) -> str:
    return git(repo,"rev-parse","--verify","HEAD^{commit}").decode().strip()


def repository_inventory(repo: Path) -> dict:
    """Compact deterministic Planner orientation; never a model-authored index."""
    def names(*args):
        raw=git(repo,*args)
        try:return [x.decode('utf-8') for x in raw.split(b'\0') if x]
        except UnicodeError as exc:raise Rejected('non-UTF8 Git path unsupported') from exc
    tracked=names('ls-files','-z');untracked=names('ls-files','--others','--exclude-standard','-z')
    all_paths=sorted(set(tracked+untracked));all_paths=[p for p in all_paths if p!='.task' and not p.startswith('.task/')]
    changed=names('diff','--name-only','--no-renames','-z','HEAD','--')+untracked
    changed=sorted(set(p for p in changed if p!='.task' and not p.startswith('.task/')))
    dirs=Counter('/'.join(p.split('/')[:2]) if '/' in p else '.' for p in all_paths)
    exts=Counter((Path(p).suffix.lower() or '<none>') for p in all_paths)
    markers={'readme','license','makefile','dockerfile','go.mod','go.sum','pyproject.toml','package.json','cargo.toml','cmakelists.txt','.gitignore','.gitattributes'}
    representative=[p for p in all_paths if len(Path(p).parts)==1 or Path(p).name.lower() in markers]
    return {'schema_version':1,'kind':'mats_repository_inventory','git_head':head(repo),
            'tracked_file_count':len(set(tracked)),'untracked_file_count':len(set(untracked)),
            'changed_path_count':len(changed),'changed_paths':changed[:256],'changed_paths_truncated':len(changed)>256,
            'root_and_marker_paths':representative[:256],'root_and_marker_paths_truncated':len(representative)>256,
            'directory_counts':[{'path':k,'files':v} for k,v in sorted(dirs.items())[:256]],
            'directory_counts_truncated':len(dirs)>256,
            'extension_counts':[{'extension':k,'files':v} for k,v in sorted(exts.items(),key=lambda x:(-x[1],x[0]))[:64]]}


def file_hash(p: Path) -> str:
    if p.is_symlink() or not p.is_file(): raise Rejected(f"not a regular evidence file: {p}")
    h=hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""): h.update(chunk)
    return h.hexdigest()


def evidence_path(repo: Path, value: str, roots: list[str]) -> Path:
    p=Path(value)
    allowed=[repo.resolve(),*[Path(r).resolve() for r in roots]]
    if not p.is_absolute(): p=repo/relative(value)
    for root in allowed:
        try: rel=p.relative_to(root)
        except ValueError: continue
        if not rel.parts: continue
        resolved=contained(root,logical_from_parts(rel.parts))
        if resolved.is_relative_to(repo/".task"): raise Rejected("domain evidence must not be stored in .task")
        return resolved
    raise Rejected("evidence outside approved roots")


def _transaction_version(value: str, workspace_snapshot: str | None) -> tuple[str | None,str | None]:
    """Validate versions produced by MATS while preserving external provenance labels."""
    if not isinstance(value,str): raise Rejected("evidence version must be a string")
    for kind in ("workspace","manifest"):
        prefix=kind+"@"
        if value.startswith(prefix):
            identity=value[len(prefix):]
            if len(identity)!=64 or any(c not in "0123456789abcdef" for c in identity) or identity=="0"*64:
                raise Rejected(f"{kind} evidence version is not a real snapshot identity")
            if workspace_snapshot is not None and identity!=workspace_snapshot:
                raise Rejected(f"{kind} evidence version does not match the candidate snapshot")
            return kind,identity
    return None,None


def materialize_evidence(repo: Path, evidence: list, roots: list[str], workspace_snapshot: str) -> list[dict]:
    """Turn model-authored paths into canonical, hash-pinned evidence records."""
    out=[]
    for item in evidence:
        if isinstance(item,str):
            path=item;kind="workspace"
        elif isinstance(item,dict) and set(item)=={"manifest"} and isinstance(item["manifest"],str):
            path=item["manifest"]
            # A semantic manifest hint may name an ordinary checksum/index file.
            # Only the script-owned MATS marker authorizes recursive expansion.
            kind="manifest" if is_mats_evidence_manifest(repo,path,roots) else "workspace"
        elif isinstance(item,dict):
            # A prior finalizer may have canonicalized this same staging file. Refresh
            # MATS-owned workspace/manifest pins on rerun; preserve external provenance.
            if set(item)=={"path","sha256","version"} and isinstance(item.get("path"),str):
                if str(item.get("version","")).startswith("workspace@"):path=item["path"];kind="workspace"
                elif str(item.get("version","")).startswith("manifest@"):path=item["path"];kind="manifest"
                else:out.append(item);continue
            else:out.append(item);continue
        else: raise Rejected("evidence draft items must be a path string, {manifest: path}, or canonical evidence object")
        p=evidence_path(repo,path,roots)
        out.append({"path":path,"sha256":file_hash(p),"version":f"{kind}@{workspace_snapshot}"})
    return out


def materialize_scope_refs(repo: Path | None, evidence: list, roots: list[str], prior: list[dict] = ()) -> list[dict]:
    """Materialize Planner-authored scope paths without making the model copy hashes.

    Existing paths retain their already-pinned record. A newly introduced path is
    content-pinned from the assigned Planner workspace. ``scope.refs`` is seed
    evidence, not candidate evidence, so its version is content-based rather than
    tied to a later Owner snapshot.
    """
    if not isinstance(evidence,list):
        raise Rejected("scope.refs must be a list of path strings")
    old={item["path"]:item for item in prior if isinstance(item,dict) and set(item)=={"path","sha256","version"}}
    out=[]
    for item in evidence:
        if isinstance(item,str):path=item
        elif isinstance(item,dict) and isinstance(item.get("path"),str):path=item["path"]
        else:raise Rejected("scope.refs items must be path strings; use delivery evidence for manifests")
        if path in old:
            out.append(old[path]);continue
        if repo is None:
            raise Rejected("new scope.refs paths require the injected --workspace finalizer argument")
        p=evidence_path(repo,path,roots);sha=file_hash(p)
        out.append({"path":path,"sha256":sha,"version":f"content@{sha}"})
    return out


def _verify_manifest(repo: Path, path: Path, roots: list[str]) -> list[dict]:
    value=load(path);require_fields(value,{"schema_version","kind","entries"})
    if value["schema_version"]!=1 or value["kind"]!="mats_evidence_manifest" or not isinstance(value["entries"],list):
        raise Rejected("invalid MATS evidence manifest")
    if len(value["entries"])>4096: raise Rejected("evidence manifest exceeds 4096 files")
    seen=set()
    for entry in value["entries"]:
        require_fields(entry,{"path","sha256"})
        if not isinstance(entry["path"],str) or not isinstance(entry["sha256"],str) or len(entry["sha256"])!=64 or any(c not in "0123456789abcdef" for c in entry["sha256"]):
            raise Rejected("invalid evidence manifest entry")
        if entry["path"] in seen: raise Rejected("duplicate evidence manifest path")
        seen.add(entry["path"]);p=evidence_path(repo,entry["path"],roots)
        if p.resolve()==path.resolve(): raise Rejected("evidence manifest cannot include itself")
        if file_hash(p)!=entry["sha256"]: raise Rejected(f"stale manifest evidence: {entry['path']}")
    return value["entries"]


def is_mats_evidence_manifest(repo: Path, value: str, roots: list[str]) -> bool:
    """Classify by content so ordinary .sha256 files remain single evidence."""
    path=evidence_path(repo,value,roots)
    if path.suffix.lower() not in {'.yaml','.yml'}:return False
    try:record=load(path)
    except Rejected:return False
    return isinstance(record,dict) and record.get('kind')=='mats_evidence_manifest'


def evidence_logical_paths(repo: Path, evidence: list, roots: list[str]) -> set[str]:
    """Project evidence declarations to repository-relative paths for scope checks."""
    paths=set()
    for item in evidence:
        manifest=False
        if isinstance(item,str):path=item
        elif isinstance(item,dict) and set(item)=={"manifest"} and isinstance(item["manifest"],str):
            path=item["manifest"];manifest=is_mats_evidence_manifest(repo,path,roots)
        elif isinstance(item,dict) and isinstance(item.get("path"),str):
            path=item["path"];manifest=str(item.get("version","")).startswith("manifest@")
        else:continue
        p=evidence_path(repo,path,roots)
        try:paths.add(p.relative_to(repo.resolve()).as_posix())
        except ValueError:continue
        if manifest:
            for entry in _verify_manifest(repo,p,roots):
                child=evidence_path(repo,entry["path"],roots)
                try:paths.add(child.relative_to(repo.resolve()).as_posix())
                except ValueError:pass
    return paths


def write_evidence_manifest(repo: Path, output: str, inputs: list[str], roots: list[str]) -> tuple[Path,int]:
    """Create a deterministic multi-file evidence index; hashes never pass through a model."""
    target=evidence_path(repo,output,roots)
    if target.suffix.lower() not in {'.yaml','.yml'}:
        raise Rejected('MATS evidence bundle output must end in .yaml or .yml; ordinary .sha256 files use an evidence row')
    if target.is_symlink(): raise Rejected("refusing symlink evidence manifest target")
    files=[]
    for value in inputs:
        p=evidence_path(repo,value,roots)
        if p.is_symlink(): raise Rejected("evidence manifest input cannot be a symlink")
        if p.is_dir():
            for child in p.rglob("*"):
                if child.resolve()==target.resolve(): continue
                if child.is_symlink(): raise Rejected("evidence manifest tree contains a symlink")
                if child.is_file(): files.append(child)
        elif p.is_file():
            if p.resolve()!=target.resolve(): files.append(p)
        else: raise Rejected(f"evidence manifest input is not a file/directory: {value}")
    unique=sorted({p.resolve() for p in files},key=lambda p:p.as_posix())
    if not unique: raise Rejected("evidence manifest has no input files")
    if len(unique)>4096: raise Rejected("evidence manifest exceeds 4096 files")
    entries=[]
    for p in unique:
        # Reapply root/symlink checks after directory expansion.
        try:path=p.relative_to(repo.resolve()).as_posix()
        except ValueError:path=p.as_posix()
        checked=evidence_path(repo,path,roots)
        entries.append({"path":path,"sha256":file_hash(checked)})
    atomic_write(target,encode({"schema_version":1,"kind":"mats_evidence_manifest","entries":entries}))
    return target,len(entries)


def verify_evidence(repo: Path, evidence: list[dict], roots: list[str], *, workspace_snapshot: str | None = None) -> None:
    for item in evidence:
        p=evidence_path(repo,item["path"],roots)
        if file_hash(p) != item["sha256"]: raise Rejected(f"stale evidence: {item['path']}")
        kind,_=_transaction_version(item["version"],workspace_snapshot)
        if kind=="manifest": _verify_manifest(repo,p,roots)


def model_evidence_paths(repo: Path, evidence: list[dict], roots: list[str]) -> list[str]:
    """Lossless path projection for model packets; hashes/versions stay Guard-private."""
    paths=[]
    for item in evidence:
        p=evidence_path(repo,item["path"],roots);kind,_=_transaction_version(item["version"],None)
        if kind=="manifest":
            _verify_manifest(repo,p,roots)
            paths.extend(entry["path"] for entry in load(p)["entries"])
        else:paths.append(item["path"])
    return list(dict.fromkeys(paths))


def snapshot(repo: Path, base: str, scope: list[str] | None = None, *, declared_read_paths: set[str] | None = None) -> dict:
    # Literal commit IDs prevent CLI option injection/ambiguous revisions.
    if len(base) not in (40,64) or any(c not in "0123456789abcdef" for c in base):
        raise Rejected("base must be an immutable Git commit ID")
    raw=git(repo,"diff","--name-only","--no-renames","-z",base,"--")
    raw+=git(repo,"diff","--cached","--name-only","--no-renames","-z",base,"--")
    raw+=git(repo,"ls-files","--others","--exclude-standard","-z")
    try: names=sorted(set(x.decode("utf-8") for x in raw.split(b"\0") if x))
    except UnicodeError as exc: raise Rejected("non-UTF8 Git path unsupported") from exc
    names=[p for p in names if p!=".task" and not p.startswith(".task/")]
    files=[]; total=0;used_read=[];declared_read_paths=declared_read_paths or set()
    for name in names:
        relative(name)
        if scope is not None and not any(name==s or name.startswith(s+"/") for s in scope):
            p=contained(repo,name)
            if name in declared_read_paths:
                if not p.exists(): raise Rejected(f"declared read-only evidence is missing: {name}")
                used_read.append({"path":name,"sha256":file_hash(p)})
            # Workspace dirtiness outside the Owner's write scope is ambient. Git
            # cannot attribute it to the user, another tool or this worker, so it
            # must neither pollute the product snapshot nor stop delivery.
            continue
        p=contained(repo,name)
        if p.exists():
            total+=p.stat().st_size
            if total>128*1024*1024: raise Rejected("snapshot exceeds 128 MiB; keep bulk evidence in approved external roots")
            files.append({"path":name,"sha256":file_hash(p)})
        else: files.append({"path":name,"deleted":True})
    if len(files)+len(used_read)>10000: raise Rejected("snapshot exceeds 10000 relevant files")
    # Git, not host stat(), owns mode identity. Windows Python and POSIX stat expose
    # different permission bits for the same checkout. Git diff is canonical across
    # those shells and includes tracked mode changes where the repository honors them.
    domain_paths=(".",":(exclude).task",":(exclude).task/**") if scope is None else tuple(scope)
    worktree_bytes=git(repo,"diff","--binary","--no-ext-diff",base,"--",*domain_paths) if domain_paths else b""
    index_bytes=git(repo,"diff","--cached","--binary","--no-ext-diff",base,"--",*domain_paths) if domain_paths else b""
    worktree=hashlib.sha256(worktree_bytes).hexdigest()
    index=hashlib.sha256(index_bytes).hexdigest()
    value={"base":base,"head":head(repo),"files":files,"worktree_diff_sha256":worktree,"index_diff_sha256":index}
    if used_read:value["declared_read_evidence"]=used_read
    return {"sha256":digest(value),"manifest":value}


def run_checks(repo: Path, required: list[str], commands: dict) -> list[dict]:
    results=[]
    for key in required:
        spec=commands.get(key)
        if not isinstance(spec,dict): raise Rejected(f"check is not in operator-approved catalog: {key}")
        argv=spec.get("argv"); timeout=spec.get("timeout_seconds",60)
        if not isinstance(argv,list) or not argv or any(not isinstance(s,str) for s in argv):
            raise Rejected("checks require argv arrays, never shell strings")
        if type(timeout) is not int or not 1<=timeout<=600: raise Rejected("invalid check timeout")
        try:
            # Outputs remain external. Avoid unbounded stdout/stderr buffering.
            cp=subprocess.run(argv,cwd=repo,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                              timeout=timeout,shell=False,check=False)
            passed=cp.returncode==0
        except (OSError,subprocess.TimeoutExpired): passed=False
        results.append({"id":key,"passed":passed,"evidence":[]})
    return results
