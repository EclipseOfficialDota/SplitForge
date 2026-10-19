import dataclasses
import os
import subprocess
import sys
import tempfile
import unittest
import venv
from pathlib import Path
from unittest.mock import patch

from splitforge.core import updater
from splitforge.core.netns import run
from splitforge.core.runner import Runner
from splitforge.protocols.manager import ProtocolManager
from splitforge.state import AppBinding, StateStore


@unittest.skipUnless(os.environ.get('SPLITFORGE_INTEGRATION') == '1' and os.geteuid() == 0,
                     'Opt-in root real environment rollback')
class RollbackLinuxTests(unittest.TestCase):
    def test_real_installed_version_state_and_root_workload_return_to_snapshot(self):
        # Build a local wheel with its declared build dependencies, then install it in
        # a disposable stable prefix. Only dependencies use the test environment.
        project = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix='splitforge-rollback-') as directory:
            base = Path(directory)
            subprocess.run([sys.executable, '-m', 'pip', 'wheel', '--no-deps',
                            '--wheel-dir', str(base / 'wheel'), str(project)], check=True, capture_output=True)
            prefix = base / 'install'
            venv.EnvBuilder(with_pip=True).create(prefix / 'venv')
            python = prefix / 'venv/bin/python'
            subprocess.run([str(python), '-m', 'pip', 'install', '--no-deps', str(next((base / 'wheel').glob('*.whl')))],
                           check=True, capture_output=True)
            site = Path(run([str(python), '-c', 'import sysconfig;print(sysconfig.get_path("purelib"))']).stdout.strip())
            dependencies = next(Path(sys.prefix).glob('lib/python*/site-packages'))
            (site / 'test-dependencies.pth').write_text(str(dependencies) + '\n')
            executable = prefix / 'venv/bin/splitforge'
            version = run([str(executable), '--version']).stdout.strip()
            state = base / 'state.json'
            store = StateStore(state)
            runner = Runner(store, ProtocolManager(store))
            binding = AppBinding('rollback-root', ['/usr/bin/sleep', '300'], user='root')
            store.save_app(binding)
            with patch.object(updater, 'BACKUP_ROOT', base / 'backups'):
                try:
                    run([str(executable), '--state', str(state), 'bind', binding.id])
                    original = store.snapshot()
                    snapshot = updater.snapshot_installation(prefix, state)
                    initializer = site / 'splitforge/__init__.py'
                    initializer.write_text('__version__ = "99.99.99"\n')
                    self.assertEqual(run([str(executable), '--version']).stdout.strip(), '99.99.99')
                    store.save_app(dataclasses.replace(store.app(binding.id), name='changed-after-update'))
                    updater.rollback(state, prefix=prefix, backup_id=snapshot.name, report=lambda _: None)
                    self.assertEqual(run([str(executable), '--version']).stdout.strip(), version)
                    self.assertEqual(store.snapshot(), original)
                    self.assertTrue(runner.running(binding))
                    pid = run(['systemctl', 'show', runner.unit(binding), '-p', 'MainPID', '--value']).stdout.strip()
                    self.assertEqual(Path(f'/proc/{pid}/ns/net').stat().st_ino, Path('/proc/1/ns/net').stat().st_ino)
                finally:
                    for app in store.apps():
                        runner.remove(app.id)
