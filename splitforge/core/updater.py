"""Update a managed installation from the official repository, without a checkout."""
from __future__ import annotations

import os
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from splitforge.core.netns import atomic_secret, require_root, run
from splitforge.state import StateStore

REPOSITORY = "https://github.com/EclipseOfficialDota/SplitForge.git"
BACKUP_ROOT = Path("/var/backups/splitforge")


def installation_prefix(prefix=None):
    if prefix is None:
        environment = Path(sys.prefix)
        if environment.name != 'venv':
            raise ValueError('Use an install.sh installation or specify --prefix /opt/splitforge')
        prefix = environment.parent
    prefix = Path(prefix).expanduser().resolve()
    if prefix == Path('/') or not all((prefix / 'venv/bin' / name).is_file() for name in ('python', 'splitforge')):
        raise ValueError('The installation prefix must contain venv/bin/python and venv/bin/splitforge')
    return prefix


def snapshot_installation(prefix, state, *, kind='update'):
    directory = BACKUP_ROOT / f'{kind}-{time.time_ns()}'
    directory.mkdir(mode=0o700, parents=True)
    if state.exists():
        with StateStore(state).operation():
            StateStore(state).snapshot()
            atomic_secret(directory / 'state.json', state.read_text())
    # Copy, never hard-link: pip replaces/mutates the active environment in place.
    shutil.copytree(prefix / 'venv', directory / 'venv', symlinks=True)
    from splitforge.web.setup import CONFIG
    if CONFIG.is_file() and not CONFIG.is_symlink():
        atomic_secret(directory / 'web.json', CONFIG.read_text())
    revision = prefix / '.splitforge-revision'
    atomic_secret(directory / 'manifest.json', json.dumps({'format': 1, 'prefix': str(prefix),
        'state': str(state), 'state_existed': state.exists(), 'created': time.time(),
        'revision': revision.read_text().strip() if revision.is_file() else ''}))
    return directory


def available_backups(prefix, state):
    result = []
    if not BACKUP_ROOT.exists():
        return result
    for directory in BACKUP_ROOT.iterdir():
        manifest = directory / 'manifest.json'
        if (directory.is_symlink() or not directory.is_dir() or directory.stat().st_mode & 0o077
                or directory.stat().st_uid != os.geteuid() or not manifest.is_file() or manifest.is_symlink()):
            continue
        try:
            data = json.loads(manifest.read_text())
            if (data.get('format') == 1 and data.get('prefix') == str(prefix)
                    and data.get('state') == str(state) and (directory / 'venv/bin/python').is_file()):
                result.append(dict(data, id=directory.name))
        except (OSError, ValueError, TypeError):
            continue
    return sorted(result, key=lambda item: item['created'], reverse=True)


def rollback(state: Path, *, prefix=None, backup_id=None, report=print):
    require_root()
    import fcntl
    prefix = installation_prefix(prefix)
    state = Path(state).expanduser().absolute()
    lock = os.open(prefix / '.update.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Another SplitForge update or rollback is already running') from None
        choices = available_backups(prefix, state)
        selected = next((item for item in choices if backup_id is None or item['id'] == backup_id), None)
        if not selected:
            raise ValueError('No matching installation backup; use splitforge rollback --list')
        source = BACKUP_ROOT / selected['id']
        if selected['state_existed']:
            StateStore(source / 'state.json').snapshot()
        current = snapshot_installation(prefix, state, kind='before-rollback')
        report(f'Current installation recovery snapshot: {current}')
        stage = prefix / f'.rollback-stage-{time.time_ns()}'
        held = prefix / f'.rollback-current-{time.time_ns()}'
        executable = prefix / 'venv/bin/splitforge'
        stopping = False
        try:
            shutil.copytree(source / 'venv', stage, symlinks=True)
            stopping = True
            run([str(executable), '--state', str(state), 'stop-all', '--preserve'], timeout=600)
            from splitforge.core.failover import MARKER, unit_name
            monitor = Path('/etc/systemd/system', unit_name(StateStore(state)))
            if monitor.is_file() and monitor.read_text().startswith(MARKER):
                # Older snapshots may not contain the failover module at all.
                # Policy-aware restore will re-enable it when needed.
                run(['systemctl', 'disable', monitor.name])
            (prefix / 'venv').rename(held)
            stage.rename(prefix / 'venv')
            if selected['state_existed']:
                atomic_secret(state, (source / 'state.json').read_text())
            else:
                state.unlink(missing_ok=True)
            marker = prefix / '.splitforge-revision'
            if selected['revision']:
                atomic_secret(marker, selected['revision'] + '\n', 0o644)
            else:
                marker.unlink(missing_ok=True)
            run([str(executable), '--state', str(state), 'restore'], timeout=600)
        except Exception as failure:
            try:
                if held.exists():
                    if (prefix / 'venv').exists():
                        try:
                            run([str(executable), '--state', str(state), 'stop-all', '--preserve'], timeout=600, check=False)
                        except (OSError, subprocess.TimeoutExpired):
                            pass
                        shutil.rmtree(prefix / 'venv')
                    held.rename(prefix / 'venv')
                    current_manifest = json.loads((current / 'manifest.json').read_text())
                    if current_manifest['state_existed']:
                        atomic_secret(state, (current / 'state.json').read_text())
                    else:
                        state.unlink(missing_ok=True)
                    if current_manifest['revision']:
                        atomic_secret(prefix / '.splitforge-revision', current_manifest['revision'] + '\n', 0o644)
                    else:
                        (prefix / '.splitforge-revision').unlink(missing_ok=True)
                if stopping:
                    run([str(executable), '--state', str(state), 'restore'], timeout=600)
            except Exception as recovery:
                raise RuntimeError(f'Rollback and recovery restart failed; retain snapshot {current}') from recovery
            raise RuntimeError(f'Rollback failed; current installation retained. Recovery snapshot: {current}') from failure
        finally:
            if stage.exists():
                shutil.rmtree(stage)
        if held.exists():
            shutil.rmtree(held)
        restart_web(prefix)
        report(f'Rolled back installation and state to {selected["id"]}; saved enabled workloads restored.')
        return selected['id']
    finally:
        os.close(lock)


def update(state: Path, *, prefix: Path | None = None, force: bool = False, report=print):
    require_root()
    import fcntl

    prefix = installation_prefix(prefix)
    if not shutil.which("git"):
        raise RuntimeError("git is required: apt-get install -y git")
    state = state.expanduser().absolute()
    lock = os.open(prefix / ".update.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("Another SplitForge update is already running") from None
        with tempfile.TemporaryDirectory(prefix="splitforge-update-") as directory:
            source = Path(directory) / "source"
            report("Downloading the latest official master revision…")
            try:
                run(["git", "-c", "credential.interactive=false", "clone", "--depth", "1", "--single-branch",
                     "--branch", "master", "--no-tags", "--", REPOSITORY, str(source)], timeout=180)
                revision = run(["git", "-C", str(source), "rev-parse", "HEAD"]).stdout.strip()
            except (RuntimeError, subprocess.TimeoutExpired):
                raise RuntimeError("Could not download the official update. Check HTTPS access to GitHub; installation was not changed.") from None
            if not re.fullmatch(r"[0-9a-f]{40}", revision):
                raise RuntimeError("Invalid upstream revision; installation was not changed")
            required = ["install.sh", "pyproject.toml", "requirements.lock", "splitforge/__init__.py"]
            if any(not (source / name).is_file() or (source / name).is_symlink() for name in required):
                raise RuntimeError("The official checkout is incomplete; installation was not changed")
            marker = prefix / ".splitforge-revision"
            if marker.is_file() and marker.read_text().strip() == revision and not force:
                report(f"Already up to date ({revision[:12]}). No workloads were restarted.")
                return
            directory = snapshot_installation(prefix, state)
            backup = directory / 'state.json' if state.exists() else None
            report(f'Private installation/settings snapshot: {directory}')
            report(f"Installing {revision[:12]} into {prefix}; managed workloads will restart…")
            environment = os.environ.copy()
            environment["SPLITFORGE_STATE"] = str(state)
            result = subprocess.run(["bash", str(source / "install.sh"), "--prefix", str(prefix),
                "--upgrade", "--restore", "--skip-proxy-cores"], env=environment)
            if result.returncode:
                raise RuntimeError(f"Update failed (exit {result.returncode}). State backup: {backup or 'no previous state'}. "
                    "Workloads may remain stopped; repair the installation, then run splitforge restore with the same state path.")
            atomic_secret(marker, revision + "\n", 0o644)
            restart_web(prefix)
            report("SplitForge updated successfully. Saved enabled assignments were restored.")
    finally:
        os.close(lock)


def restart_web(prefix):
    command = run(['systemctl', 'show', 'splitforge-web.service', '-p', 'ExecStart', '--value'], check=False).stdout
    paths = [str(prefix / 'venv/bin' / name) for name in ('python', 'splitforge')]
    link = Path('/usr/local/bin/splitforge')
    if link.resolve() == (prefix / 'venv/bin/splitforge').resolve():
        paths.append(str(link))
    if (any(f'path={path} ;' in command for path in paths)
            and run(['systemctl', 'is-active', '--quiet', 'splitforge-web.service'], check=False).returncode == 0):
        run(['systemctl', 'restart', 'splitforge-web.service'], timeout=1900)
