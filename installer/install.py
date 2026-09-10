#!/usr/bin/env python3
"""Install MATS into a Codex skills directory and build its private runtime."""
from __future__ import annotations

import argparse
import filecmp
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import venv
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE = REPO_ROOT / 'skill' / 'multi-agent-task-split'
REQUIREMENTS = Path(__file__).resolve().with_name('requirements.txt')
SKILL_NAME = 'multi-agent-task-split'


class InstallError(RuntimeError):
    pass


def default_skills_dir() -> Path:
    codex_home = os.environ.get('CODEX_HOME')
    if codex_home:
        return Path(codex_home).expanduser() / 'skills'
    return Path.home() / '.codex' / 'skills'


def runtime_python(skill_root: Path) -> Path:
    return skill_root / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')


def run(argv: list[str], *, cwd: Path) -> None:
    shown = subprocess.list2cmdline(argv) if os.name == 'nt' else ' '.join(argv)
    print(f'> {shown}')
    cp = subprocess.run(argv, cwd=cwd, text=True, check=False)
    if cp.returncode:
        raise InstallError(f'command failed with exit code {cp.returncode}: {shown}')


def copy_payload(target: Path) -> None:
    if not SOURCE.is_dir():
        raise InstallError(f'skill payload not found: {SOURCE}')
    shutil.copytree(
        SOURCE,
        target,
        copy_function=shutil.copy,
        ignore=shutil.ignore_patterns('.venv', '__pycache__', '*.pyc'),
    )
    for forbidden in ('install.py', 'install.cmd', 'requirements.txt', 'runtime'):
        if (target / forbidden).exists():
            raise InstallError(f'user installer/runtime source leaked into skill payload: {forbidden}')
    launcher=target/'bin'/'mats'
    launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def build_runtime(skill_root: Path) -> None:
    print(f'Creating isolated runtime: {skill_root / ".venv"}')
    uv = shutil.which('uv')
    if uv:
        run([uv, 'venv', '--python', sys.executable, str(skill_root / '.venv')], cwd=skill_root)
    else:
        # Compatibility fallback for user machines without uv. The runtime is still
        # destination-local and the dependency remains exactly pinned.
        venv.EnvBuilder(with_pip=True, clear=False, symlinks=False).create(skill_root / '.venv')
    py = runtime_python(skill_root)
    if not py.is_file():
        raise InstallError(f'venv did not create its interpreter: {py}')
    if uv:
        # Copy wheels instead of hardlinking uv's cache. On Windows a loaded DLL in
        # the cache can otherwise prevent deletion of an upgraded Skill backup.
        run([uv, 'pip', 'install', '--python', str(py), '--link-mode', 'copy', '--only-binary=:all:', '--requirement', str(REQUIREMENTS)], cwd=skill_root)
    else:
        run([str(py), '-I', '-m', 'pip', 'install', '--disable-pip-version-check', '--no-input',
             '--only-binary=:all:', '--requirement', str(REQUIREMENTS)], cwd=skill_root)
    run([str(py), '-I', '-B', '-X', 'utf8', str(skill_root / 'scripts' / 'mats.py'), 'doctor'], cwd=skill_root)


def replace_directory(source: Path, target: Path) -> None:
    """Rename a directory, tolerating short-lived Windows process/AV handles."""
    attempts = 8 if os.name == 'nt' else 1
    for attempt in range(attempts):
        try:
            source.replace(target)
            return
        except PermissionError:
            if attempt + 1 == attempts:
                raise
            time.sleep(0.05 * (2 ** attempt))


def payload_files(root: Path) -> dict[Path, Path]:
    """Return regular payload files without entering the private runtime."""
    result = {}
    for base, dirs, files in os.walk(root, followlinks=False):
        base_path = Path(base)
        dirs[:] = [name for name in dirs if name != '.venv']
        for name in dirs + files:
            path = base_path / name
            if path.is_symlink():
                raise InstallError(f'refusing in-place update through payload symlink: {path}')
        for name in files:
            path = base_path / name
            result[path.relative_to(root)] = path
    return result


def overlay_payload(source: Path, target: Path) -> None:
    """Atomically replace payload files while retaining target/.venv."""
    incoming = payload_files(source)
    existing = payload_files(target)
    for relative, source_file in incoming.items():
        destination_file = target / relative
        # A running host may hold model-facing metadata open on Windows. Do not
        # replace byte-identical payload files: it is unnecessary and can turn an
        # otherwise safe in-place upgrade into a sharing-violation failure.
        if destination_file.is_file() and filecmp.cmp(source_file, destination_file, shallow=False):
            continue
        destination_file.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(prefix=f'.{destination_file.name}.install-', dir=destination_file.parent)
        os.close(fd)
        temporary = Path(temporary_name)
        try:
            shutil.copy(source_file, temporary)
            os.replace(temporary, destination_file)
        finally:
            if temporary.exists():
                temporary.unlink()
    for relative in existing.keys() - incoming.keys():
        (target / relative).unlink()
    for base, dirs, _files in os.walk(target, topdown=False, followlinks=False):
        base_path = Path(base)
        if base_path == target or '.venv' in base_path.relative_to(target).parts:
            continue
        try:
            base_path.rmdir()
        except OSError:
            pass


def update_locked_destination(stage: Path, destination: Path, backup: Path) -> None:
    """Update only the payload when a live Windows process pins the Skill directory."""
    shutil.copytree(destination, backup, copy_function=shutil.copy, ignore=shutil.ignore_patterns('.venv'))
    try:
        overlay_payload(stage, destination)
        run([str(runtime_python(destination)), '-I', '-B', '-X', 'utf8', str(destination / 'scripts' / 'mats.py'), 'doctor'], cwd=destination)
    except Exception:
        try:
            overlay_payload(backup, destination)
        except Exception as rollback_error:
            raise InstallError(f'in-place update and rollback failed; preserved backup at {backup}: {rollback_error}')
        shutil.rmtree(backup)
        raise
    shutil.rmtree(backup)
    print('Updated existing destination payload in place and retained its verified isolated runtime.')


def install(skills_dir: Path, *, force: bool) -> Path:
    skills_dir = skills_dir.expanduser().resolve()
    skills_dir.mkdir(parents=True, exist_ok=True)
    destination = skills_dir / SKILL_NAME
    if destination.exists() and not force:
        raise InstallError(f'{destination} already exists; rerun with --force to replace it')
    if destination.is_symlink():
        raise InstallError(f'refusing to replace symlink destination: {destination}')

    backup = skills_dir / f'.{SKILL_NAME}.backup'
    if backup.exists():
        raise InstallError(f'stale installer backup requires manual inspection: {backup}')
    stage = Path(tempfile.mkdtemp(prefix=f'.{SKILL_NAME}.install-', dir=skills_dir))
    try:
        stage.rmdir()
        copy_payload(stage)
        build_runtime(stage)
        if destination.exists() and os.name == 'nt':
            # A desktop host may keep Python extensions or metadata open long after
            # a command returns. Updating payload only avoids moving/deleting that
            # live private runtime and is the normal Windows upgrade path.
            update_locked_destination(stage, destination, backup)
            return destination
        if destination.exists():
            replace_directory(destination, backup)
        try:
            replace_directory(stage, destination)
        except Exception:
            if backup.exists():
                replace_directory(backup, destination)
            raise
        try:
            run([str(runtime_python(destination)), '-I', '-B', '-X', 'utf8', str(destination / 'scripts' / 'mats.py'), 'doctor'], cwd=destination)
        except Exception:
            if destination.exists():
                shutil.rmtree(destination)
            if backup.exists():
                replace_directory(backup, destination)
            raise
        if backup.exists():
            shutil.rmtree(backup)
        return destination
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skills-dir', type=Path, default=default_skills_dir())
    parser.add_argument('--force', action='store_true', help='replace an existing installed copy after staging succeeds')
    args = parser.parse_args(argv)
    if sys.version_info < (3, 10):
        print('MATS_INSTALL_ERROR: Python 3.10+ is required', file=sys.stderr)
        return 2
    try:
        destination = install(args.skills_dir, force=args.force)
    except (InstallError, OSError, subprocess.SubprocessError) as exc:
        print(f'MATS_INSTALL_ERROR: {exc}', file=sys.stderr)
        return 2
    print(f'MATS installed: {destination}')
    print(f'Runtime: {runtime_python(destination)}')
    print('Installed payload timestamps reflect this installation copy.')
    print('Active Control sessions do not hot reload Skill updates; start a new Control session.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
