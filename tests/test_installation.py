import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
import yaml


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / 'installer' / 'install.py'
SOURCE_SKILL = ROOT / 'skill' / 'multi-agent-task-split'


class UserInstallation(unittest.TestCase):
    def test_user_installer_copies_skill_and_builds_isolated_runtime(self):
        self.assertTrue(INSTALLER.is_file(), 'missing user-facing installer/installation entrypoint')
        with tempfile.TemporaryDirectory() as td:
            skills = Path(td) / 'skills with spaces'
            argv = [sys.executable, str(INSTALLER), '--skills-dir', str(skills)]
            if os.name == 'nt':
                argv = [os.environ.get('COMSPEC', 'cmd.exe'), '/d', '/c', str(ROOT / 'install.cmd'), '--skills-dir', str(skills)]
            cp = subprocess.run(
                argv,
                text=True,
                capture_output=True,
                timeout=240,
            )
            self.assertEqual(cp.returncode, 0, cp.stdout + cp.stderr)
            self.assertIn('Installed payload timestamps reflect this installation copy',cp.stdout)
            self.assertIn('Active Control sessions do not hot reload Skill updates',cp.stdout)
            installed = skills / 'multi-agent-task-split'
            py = installed / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
            self.assertTrue(py.is_file())
            if os.name != 'nt':self.assertTrue(os.access(installed / 'bin' / 'mats', os.X_OK))
            self.assertFalse((installed / 'install.py').exists())
            self.assertFalse((installed / 'install.cmd').exists())
            self.assertFalse((installed / 'requirements.txt').exists())
            self.assertFalse((installed / 'runtime').exists())
            payload_files = [p.relative_to(installed).as_posix() for p in installed.rglob('*') if p.is_file() and '.venv' not in p.relative_to(installed).parts]
            self.assertFalse(any('__pycache__' in rel or rel.endswith('.pyc') for rel in payload_files))

            doctor = subprocess.run(
                [str(py), '-I', '-B', str(installed / 'scripts' / 'mats.py'), 'doctor'],
                text=True,
                capture_output=True,
                timeout=30,
            )
            self.assertEqual(doctor.returncode, 0, doctor.stdout + doctor.stderr)
            result = yaml.safe_load(doctor.stdout)
            self.assertEqual(result['version'], '1.1.0')
            self.assertTrue(result['isolated_runtime'])
            self.assertTrue(Path(result['yaml_module']).resolve().is_relative_to((installed / '.venv').resolve()))

            entrypoints = {
                'mats.py': ['doctor'],
                'dispatchctl.py': ['doctor'],
                'role_spawn.py': ['--help'],
            }
            for name,args in entrypoints.items():
                managed = subprocess.run([str(py), '-I', '-B', str(installed / 'scripts' / name), *args], text=True, capture_output=True, timeout=30)
                self.assertEqual(managed.returncode, 0, managed.stdout + managed.stderr)
                unmanaged = subprocess.run([sys.executable, str(installed / 'scripts' / name), *args], text=True, capture_output=True, timeout=30)
                self.assertNotEqual(unmanaged.returncode, 0)
                self.assertIn('MATS_RUNTIME_ERROR', unmanaged.stdout + unmanaged.stderr)

            refused = subprocess.run(argv, text=True, capture_output=True, timeout=60)
            self.assertNotEqual(refused.returncode, 0)
            self.assertIn('already exists', refused.stdout + refused.stderr)

            replaced = subprocess.run([*argv, '--force'], text=True, capture_output=True, timeout=240)
            self.assertEqual(replaced.returncode, 0, replaced.stdout + replaced.stderr)
            self.assertTrue(py.is_file())

    def test_windows_installer_is_outside_the_skill_payload(self):
        self.assertTrue((ROOT / 'install.cmd').is_file())
        self.assertFalse((SOURCE_SKILL / 'install.cmd').exists())
        self.assertFalse((SOURCE_SKILL / 'install.py').exists())
        self.assertIn('copy_function=shutil.copy',INSTALLER.read_text())
        self.assertIn('update_locked_destination',INSTALLER.read_text())
        self.assertIn('overlay_payload(stage, destination)',INSTALLER.read_text())
        self.assertIn('filecmp.cmp(source_file, destination_file, shallow=False)',INSTALLER.read_text())
        self.assertIn("destination.exists() and os.name == 'nt'",INSTALLER.read_text())

    def test_skill_payload_has_no_vendored_runtime_or_unused_bridge(self):
        files = [p for p in SOURCE_SKILL.rglob('*') if p.is_file()]
        rels = [p.relative_to(SOURCE_SKILL).as_posix() for p in files]
        self.assertFalse(any(rel.startswith('runtime/') for rel in rels))
        self.assertNotIn('scripts/native_boundary.py', rels)


if __name__ == '__main__':
    unittest.main()
