"""Read-only validation for the current .task layout.

This module deliberately does not migrate state.  A repository may have an
arbitrarily complex history, so moves, ref rewrites and native lifecycle
reconciliation require operator judgement from the migration guide.
"""
from __future__ import annotations

from pathlib import Path

from common import ROOT, Rejected, digest, load, relative
from records import MILESTONE_FOLDERS, MILESTONE_ID


TARGET_RELEASE = '1.0.0'
LAYOUT = 'milestone-nested-v1'
ALLOWED_TOP_LEVEL_DIRS = frozenset({
    'archive', 'config', 'directives', 'operations', 'payloads', 'provenance', 'tmp',
})
ALLOWED_TOP_LEVEL_FILES = frozenset({'coordinator.lock', 'operator.yaml', 'semantic.yaml'})
REMOVED_LOCKS = frozenset({'admission.lock', 'semantic.lock'})


def _issue(code, path, detail):
    return {'reason_code': code, 'path': path, 'detail': detail}


def _logical(root, path):
    return path.relative_to(root).as_posix()


def _walk_refs(value, source, issues, root):
    """Check exact path+sha256 mappings; other path-bearing records are not refs."""
    if isinstance(value, dict):
        keys = set(value)
        if {'path', 'sha256'} <= keys and 'version' not in keys:
            if keys != {'path', 'sha256'}:
                issues.append(_issue('TASK_REF_FIELDS_INVALID', source,
                    f'internal ref has unexpected fields: {sorted(keys - {"path", "sha256"})}'))
            logical = value.get('path')
            if not isinstance(logical, str) or '\\' in logical:
                issues.append(_issue('TASK_REF_PATH_INVALID', source,
                    'internal refs require a canonical POSIX relative path'))
                return
            try:
                logical = relative(logical)
            except Rejected as exc:
                issues.append(_issue('TASK_REF_PATH_INVALID', source, str(exc)))
                return
            parts = logical.split('/')
            if parts[0] in {'tmp', 'archive'}:
                issues.append(_issue('TASK_REF_TRANSIENT', source,
                    f'canonical internal ref cannot target {logical}'))
            elif parts[0] in MILESTONE_FOLDERS:
                issues.append(_issue('TASK_REF_LEGACY_TOP_LEVEL', source,
                    f'internal ref {logical} is not milestone-nested'))
            elif len(parts) >= 2 and parts[1] in MILESTONE_FOLDERS and not MILESTONE_ID.fullmatch(parts[0]):
                issues.append(_issue('TASK_REF_MILESTONE_INVALID', source,
                    f'internal ref {logical} has an invalid milestone namespace'))
            target = root.joinpath(*parts)
            try:
                target.resolve().relative_to(root.resolve())
            except ValueError:
                issues.append(_issue('TASK_REF_PATH_INVALID', source,
                    f'internal ref {logical} escapes .task'))
                return
            if not target.is_file():
                issues.append(_issue('TASK_REF_MISSING', source,
                    f'internal ref target does not exist: {logical}'))
                return
            try:
                actual = digest(load(target))
            except (Rejected, OSError) as exc:
                issues.append(_issue('TASK_REF_TARGET_INVALID', source,
                    f'internal ref target cannot be verified: {logical}: {exc}'))
                return
            if value.get('sha256') != actual:
                issues.append(_issue('TASK_REF_HASH_MISMATCH', source,
                    f'internal ref digest does not match: {logical}'))
            return
        for child in value.values():
            _walk_refs(child, source, issues, root)
    elif isinstance(value, list):
        for child in value:
            _walk_refs(child, source, issues, root)


def validate_task_layout(repo):
    """Return a deterministic report without creating or changing any path."""
    repo = Path(repo).resolve()
    root = repo / '.task'
    guide = (ROOT / 'references' / 'migration.md').resolve().as_posix()
    issues = []
    if not root.exists():
        return {'valid': True, 'target_release': TARGET_RELEASE, 'layout': LAYOUT,
                'task_root': root.as_posix(), 'initialized': False, 'issues': []}
    if not root.is_dir() or root.is_symlink():
        issues.append(_issue('TASK_ROOT_INVALID', '.task', '.task must be a real directory, not a file or symlink'))
    else:
        for entry in sorted(root.iterdir(), key=lambda item: item.name):
            name = entry.name
            if entry.is_symlink():
                issues.append(_issue('TASK_SYMLINK_FORBIDDEN', name, 'symlinks are forbidden in .task'))
                continue
            if name in REMOVED_LOCKS:
                issues.append(_issue('TASK_REMOVED_LOCK_PRESENT', name,
                    'old manually maintained lock carrier is not part of the current layout'))
            if entry.is_dir():
                if name in MILESTONE_FOLDERS:
                    issues.append(_issue('TASK_LEGACY_TOP_LEVEL_DIR', name,
                        'long-lived typed directories must be nested under a milestone'))
                elif name.startswith('m') and not MILESTONE_ID.fullmatch(name):
                    issues.append(_issue('TASK_MILESTONE_NAME_INVALID', name,
                        'milestone directory must be m<number> or m<number>_<milestone-slug>'))
                elif not MILESTONE_ID.fullmatch(name) and name not in ALLOWED_TOP_LEVEL_DIRS:
                    issues.append(_issue('TASK_UNKNOWN_TOP_LEVEL_ENTRY', name,
                        'directory is not part of the current .task layout'))
            elif name not in ALLOWED_TOP_LEVEL_FILES and name not in REMOVED_LOCKS:
                issues.append(_issue('TASK_UNKNOWN_TOP_LEVEL_ENTRY', name,
                    'file is not part of the current .task layout'))

        semantic = root / 'semantic.yaml'
        if semantic.exists():
            try:
                state = load(semantic)
                plan_id = state.get('plan', {}).get('plan_id') if isinstance(state, dict) else None
                if not MILESTONE_ID.fullmatch(plan_id or ''):
                    issues.append(_issue('TASK_ACTIVE_MILESTONE_INVALID', 'semantic.yaml',
                        'semantic plan.plan_id must be m<number> or m<number>_<milestone-slug>'))
                elif not (root / plan_id).is_dir():
                    issues.append(_issue('TASK_ACTIVE_MILESTONE_MISSING', 'semantic.yaml',
                        f'active milestone directory does not exist: {plan_id}'))
            except (Rejected, OSError) as exc:
                issues.append(_issue('TASK_YAML_INVALID', 'semantic.yaml', str(exc)))

        for milestone in sorted((p for p in root.iterdir() if p.is_dir() and not p.is_symlink() and MILESTONE_ID.fullmatch(p.name)), key=lambda p: p.name):
            for entry in sorted(milestone.iterdir(), key=lambda item: item.name):
                logical = _logical(root, entry)
                if entry.is_symlink():
                    issues.append(_issue('TASK_SYMLINK_FORBIDDEN', logical, 'symlinks are forbidden in milestone state'))
                elif not entry.is_dir() or entry.name not in MILESTONE_FOLDERS:
                    issues.append(_issue('TASK_MILESTONE_ENTRY_INVALID', logical,
                        'milestones contain only fixed long-lived typed directories'))
            for folder in sorted(MILESTONE_FOLDERS):
                typed = milestone / folder
                if not typed.is_dir():
                    continue
                for artifact in sorted(typed.iterdir(), key=lambda item: item.name):
                    logical = _logical(root, artifact)
                    if not artifact.is_file() or artifact.is_symlink() or artifact.suffix != '.yaml':
                        issues.append(_issue('TASK_ARTIFACT_FILE_INVALID', logical,
                            'long-lived typed directories contain only regular .yaml files'))
                    elif folder == 'packets' and not (
                            artifact.name.startswith('p') and len(artifact.name) == 12 and
                            artifact.name[1:7].isdigit() and artifact.suffix == '.yaml'):
                        issues.append(_issue('TASK_PACKET_NAME_INVALID', logical,
                            'packet filename must be pNNNNNN.yaml'))

        # tmp/archive are deliberately excluded: they are staging/operator history.
        yaml_paths = []
        for path in root.rglob('*.yaml'):
            try:
                logical = _logical(root, path)
            except ValueError:
                continue
            if path.is_symlink() or logical.startswith('tmp/') or logical.startswith('archive/'):
                continue
            yaml_paths.append((logical, path))
        for logical, path in sorted(yaml_paths):
            try:
                value = load(path)
            except (Rejected, OSError) as exc:
                if logical != 'semantic.yaml' or not any(i['reason_code'] == 'TASK_YAML_INVALID' and i['path'] == logical for i in issues):
                    issues.append(_issue('TASK_YAML_INVALID', logical, str(exc)))
                continue
            _walk_refs(value, logical, issues, root)

    issues.sort(key=lambda item: (item['path'], item['reason_code'], item['detail']))
    out = {'valid': not issues, 'target_release': TARGET_RELEASE, 'layout': LAYOUT,
           'task_root': root.as_posix(), 'initialized': (root / 'semantic.yaml').is_file(),
           'issues': issues}
    if issues:
        out['reason_code'] = 'TASK_MIGRATION_REQUIRED'
        out['migration_guide'] = guide
        out['note'] = 'Read-only validation only; no files, refs, locks, or native sessions were changed.'
    return out
