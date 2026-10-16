"""Update a managed installation from the official repository, without a checkout."""
from __future__ import annotations

import os
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


def update(state: Path, *, prefix: Path | None = None, force: bool = False, report=print):
    require_root()
    import fcntl

    if prefix is None:
        environment = Path(sys.prefix)
        if environment.name != "venv":
            raise ValueError("Use an install.sh installation or specify --prefix /opt/splitforge")
        prefix = environment.parent
    prefix = prefix.expanduser().resolve()
    if prefix == Path("/") or not all((prefix / "venv/bin" / name).is_file() for name in ("python", "splitforge")):
        raise ValueError("The installation prefix must contain venv/bin/python and venv/bin/splitforge")
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
            backup = None
            store = StateStore(state)
            if state.exists():
                with store.operation():
                    store.snapshot()  # Refuse invalid state before stopping any workloads.
                    backup = BACKUP_ROOT / f"update-{time.strftime('%Y%m%d-%H%M%S', time.gmtime())}-{time.time_ns()}" / "state.json"
                    atomic_secret(backup, state.read_text(encoding="utf-8"))
                report(f"Private state backup: {backup}")
            report(f"Installing {revision[:12]} into {prefix}; managed workloads will restart…")
            environment = os.environ.copy()
            environment["SPLITFORGE_STATE"] = str(state)
            result = subprocess.run(["bash", str(source / "install.sh"), "--prefix", str(prefix),
                "--upgrade", "--restore", "--skip-proxy-cores"], env=environment)
            if result.returncode:
                raise RuntimeError(f"Update failed (exit {result.returncode}). State backup: {backup or 'no previous state'}. "
                    "Workloads may remain stopped; repair the installation, then run splitforge restore with the same state path.")
            atomic_secret(marker, revision + "\n", 0o644)
            report("SplitForge updated successfully. Saved enabled assignments were restored.")
    finally:
        os.close(lock)
