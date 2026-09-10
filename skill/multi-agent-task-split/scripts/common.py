"""Small fail-closed cross-platform primitives for the semantic control plane."""
from __future__ import annotations
import hashlib
import math
import os
import re
import sys
import tempfile
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

SCHEMA_VERSION = 9
ROOT = Path(__file__).resolve().parents[1]
import yaml
from yaml.events import AliasEvent

MAX_YAML_BYTES = 4 * 1024 * 1024
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}\Z")

class Rejected(ValueError):
    """Expected policy/validation failure; no state change."""
    def __init__(self,message: str,*,code: str='REJECTED',next_operation: dict | None=None):
        super().__init__(message)
        if not isinstance(code,str) or not ID.fullmatch(code):raise ValueError('invalid rejection reason code')
        self.code=code;self.next_operation=next_operation

def rejection_payload(exc: Exception) -> dict:
    """Expose stable machine routing without removing readable diagnostics."""
    out={'error':type(exc).__name__,'reason_code':getattr(exc,'code','REJECTED'),'detail':str(exc)}
    next_operation=getattr(exc,'next_operation',None)
    if next_operation is not None:out['next_operation']=next_operation
    return out

def managed_runtime_status() -> dict:
    """Describe whether this interpreter and PyYAML belong to the installed venv."""
    expected=(ROOT/'.venv').resolve()
    actual=Path(sys.prefix).resolve()
    base=Path(sys.base_prefix).resolve()
    yaml_path=Path(yaml.__file__).resolve()
    try: yaml_path.relative_to(expected);yaml_local=True
    except ValueError: yaml_local=False
    return {'isolated_runtime':actual == expected and actual != base and yaml_local,
            'python':str(Path(sys.executable).resolve()),'yaml_module':str(yaml_path)}

def require_managed_runtime() -> dict:
    """Fail closed unless an entrypoint runs in this installed Skill's venv."""
    status=managed_runtime_status()
    if not status['isolated_runtime']:
        raise RuntimeError(f'MATS_RUNTIME_ERROR: use the installed bin/mats launcher for {ROOT}')
    return status

class StrictLoader(yaml.SafeLoader):
    def compose_node(self, parent, index):
        if self.check_event(AliasEvent):
            raise Rejected("YAML aliases are not accepted")
        self._depth = getattr(self, "_depth", 0) + 1
        if self._depth > 40:
            raise Rejected("YAML nesting exceeds 40")
        try:
            return super().compose_node(parent, index)
        finally:
            self._depth -= 1
    def construct_mapping(self, node, deep=False):
        out = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str) or key == "<<":
                raise Rejected("YAML mapping keys must be strings; merge keys forbidden")
            if key in out:
                raise Rejected(f"duplicate YAML key: {key}")
            out[key] = self.construct_object(value_node, deep=deep)
        return out

def plain(value: Any, depth: int = 0) -> None:
    if depth > 40:
        raise Rejected("object nesting exceeds 40")
    if isinstance(value, dict):
        if any(not isinstance(k, str) for k in value):
            raise Rejected("mapping keys must be strings")
        for v in value.values(): plain(v, depth+1)
    elif isinstance(value, list):
        for v in value: plain(v, depth+1)
    elif isinstance(value, float):
        if not math.isfinite(value): raise Rejected("nonfinite numbers forbidden")
    elif value is not None and type(value) not in (str, int, bool):
        raise Rejected(f"unsupported value: {type(value).__name__}")

def parse(data: bytes) -> Any:
    if len(data) > MAX_YAML_BYTES: raise Rejected("YAML exceeds byte limit")
    try:
        obj = yaml.load(data.decode("utf-8"), Loader=StrictLoader)
    except (yaml.YAMLError, UnicodeError) as exc:
        raise Rejected(f"invalid YAML: {exc}") from exc
    plain(obj)
    return obj

def load(path: str | Path) -> Any:
    p = Path(path)
    if p.suffix.lower() not in {".yaml", ".yml"}: raise Rejected("expected YAML file")
    with p.open("rb") as f: return parse(f.read(MAX_YAML_BYTES+1))

class CanonicalDumper(yaml.SafeDumper):
    def ignore_aliases(self, data):
        return True

def encode(obj: Any) -> bytes:
    plain(obj)
    return yaml.dump(obj, Dumper=CanonicalDumper, allow_unicode=True, sort_keys=True, width=100).encode("utf-8")

def emit_utf8(value: Any, *, error: bool = False) -> None:
    """Write exact UTF-8 bytes even when Windows stdio advertises a legacy code page."""
    data=value if isinstance(value,bytes) else value.encode('utf-8') if isinstance(value,str) else encode(value)
    stream=sys.stderr if error else sys.stdout
    binary=getattr(stream,'buffer',None)
    if binary is not None:
        binary.write(data);binary.flush()
    else:
        # unittest/caller StringIO has no byte buffer.
        stream.write(data.decode('utf-8'));stream.flush()

def digest(obj: Any) -> str:
    return hashlib.sha256(encode(obj)).hexdigest()

def identifier(value: Any) -> str:
    if not isinstance(value, str) or not ID.fullmatch(value) or ".." in value:
        raise Rejected(f"invalid identifier: {value!r}")
    return value

def relative(value: Any) -> str:
    """Validate a canonical POSIX logical path used inside semantic refs."""
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise Rejected("invalid relative path")
    p = PurePosixPath(value)
    if p.is_absolute() or any(x in {"", ".", ".."} for x in p.parts):
        raise Rejected(f"unsafe relative path: {value}")
    # Reject drive-like or URI-like first components. Logical refs never contain colons.
    if any(":" in x for x in p.parts):
        raise Rejected(f"unsafe relative path: {value}")
    return p.as_posix()

def logical_from_parts(parts) -> str:
    """Convert already-relative host path parts to canonical POSIX logical form."""
    parts = tuple(str(x) for x in parts)
    if not parts:
        raise Rejected("empty relative path")
    return relative(PurePosixPath(*parts).as_posix())

def logical_relative(root: Path, path: Path) -> str:
    """Return a canonical POSIX ref even when host Path.relative_to() uses backslashes."""
    root = Path(root).resolve()
    p = Path(path).resolve()
    try:
        rel = p.relative_to(root)
    except ValueError as exc:
        raise Rejected("path is outside control root") from exc
    return logical_from_parts(rel.parts)

def normalize_windows_relative(value: str) -> str:
    """Adapter helper for a host-produced Windows relative path; never accepts absolute paths."""
    p = PureWindowsPath(value)
    if p.is_absolute() or p.drive or p.root:
        raise Rejected("Windows host path is not relative")
    return logical_from_parts(p.parts)

def contained(root: Path, rel: str) -> Path:
    rel = relative(rel)
    root = Path(root).resolve()
    parts = PurePosixPath(rel).parts
    cur = root
    for part in parts:
        cur = cur / part
        if cur.is_symlink(): raise Rejected(f"symlink forbidden in control/evidence path: {cur}")
    p = root.joinpath(*parts)
    try:
        p.resolve().relative_to(root)
    except ValueError as exc:
        raise Rejected("path escapes root") from exc
    return p

def fsync_dir(path: Path) -> None:
    """Best-effort directory durability where the host exposes directory fsync."""
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        fd = os.open(path, flags)
    except OSError:
        return
    try:
        try: os.fsync(fd)
        except OSError: pass
    finally:
        os.close(fd)

def atomic_write(path: Path, data: bytes, *, immutable: bool = False) -> None:
    """Cross-platform atomic replace; immutable writes use atomic hard-link create."""
    if path.is_symlink(): raise Rejected("refusing symlink target")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".write-", dir=path.parent)
    tmp = Path(name)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data); f.flush(); os.fsync(f.fileno())
        if immutable:
            # Hard-link creation is create-if-absent on POSIX and NTFS. Fail closed on
            # filesystems that cannot provide this property; do not fall back to TOCTOU.
            os.link(tmp, path)
        else:
            os.replace(tmp, path)
        fsync_dir(path.parent)
    finally:
        try: tmp.unlink(missing_ok=True)
        except OSError: pass

def require_fields(obj: Any, required: set[str], optional: set[str] = frozenset()) -> None:
    if not isinstance(obj, dict): raise Rejected("expected an object")
    missing, extra = required-set(obj), set(obj)-required-optional
    if missing or extra: raise Rejected(f"fields: missing={sorted(missing)}, unexpected={sorted(extra)}")
