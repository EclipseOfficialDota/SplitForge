"""Persistent, fail-closed application failover; never uses the host Direct route."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import logging
import os
import signal
import sys
import threading
from pathlib import Path

from splitforge.core.netns import atomic_secret, require_root, run, unit_word
from splitforge.core.diagnostics import namespace_checks
from splitforge.core.runner import Runner
from splitforge.protocols.manager import ProtocolManager
from splitforge.state import StateStore

MARKER = '# SplitForge automatic failover\n'


def unit_name(store: StateStore):
    return 'splitforge-failover-' + hashlib.sha256(str(store.path.resolve()).encode()).hexdigest()[:12] + '.service'


def ensure_service(store: StateStore):
    require_root()
    path = Path('/etc/systemd/system', unit_name(store))
    if path.exists() and not path.read_text().startswith(MARKER):
        raise ValueError('Refusing to replace an unrelated failover service')
    command = [sys.executable, '-m', 'splitforge.core.failover', '--state', str(store.path.resolve())]
    text = MARKER + f'''[Unit]
Description=SplitForge application tunnel failover
After=network-online.target
Wants=network-online.target
[Service]
Type=simple
User=root
ExecStart={' '.join(unit_word(word) for word in command)}
Restart=on-failure
RestartSec=5
UMask=0077
TimeoutStopSec=5min
KillMode=mixed
[Install]
WantedBy=multi-user.target
'''
    if not path.exists() or path.read_text() != text:
        atomic_secret(path, text, 0o644)
        run(['systemctl', 'daemon-reload'])
    run(['systemctl', 'enable', '--now', path.name])


class FailoverMonitor:
    def __init__(self, store, manager=None, runner=None, *, threshold=2, stop=None, report=None):
        if threshold < 1:
            raise ValueError('Failure threshold must be positive')
        self.store = store
        self.manager = manager or ProtocolManager(store)
        self.runner = runner or Runner(store, self.manager)
        self.threshold = threshold
        self.stop = stop or threading.Event()
        self.report = report or logging.info
        self.failures = {}

    def cycle(self):
        cache = {}
        def healthy(profile_id, *, start=False):
            if profile_id in cache and (cache[profile_id] or not start):
                return cache[profile_id]
            try:
                status = self.manager.status(profile_id)
                if start and not status['active']:
                    self.manager.start(profile_id)
                    status = self.manager.status(profile_id)
                profile = self.store.profile(profile_id)
                if (not status['active'] or not status['namespace']
                        or not all(ok for _, ok, _ in namespace_checks(self.manager, profile))):
                    cache[profile_id] = False
                else:
                    self.manager.test(profile_id, persist=False)
                    cache[profile_id] = True
            except Exception:
                cache[profile_id] = False
            return cache[profile_id]
        apps = [app for app in self.store.apps() if app.enabled and app.failover_enabled]
        self.failures = {key: value for key, value in self.failures.items() if key in {app.id for app in apps}}
        for app in apps:
            if self.stop.is_set():
                return
            try:
                if healthy(app.profile_id):
                    self.failures[app.id] = 0
                    if not self.runner.running(app) and not self.stop.is_set():
                        self.runner.bind(app.id, app.profile_id, preserve_failover=True, expected=app)
                    continue
                self.failures[app.id] = self.failures.get(app.id, 0) + 1
                if self.failures[app.id] < self.threshold:
                    continue
                # Stop first; retain intent even when both tunnels are down.
                self.runner.suspend(app)
                if self.stop.is_set():
                    return
                target = app.backup_profile_id if app.profile_id == app.primary_profile_id else app.primary_profile_id
                if healthy(target, start=True) and not self.stop.is_set():
                    updated = self.runner.bind(app.id, target, preserve_failover=True, expected=app)
                    if self.runner.running(updated):
                        self.failures[app.id] = 0
                        self.report(f'App {app.id}: tunnel {app.profile_id} -> {updated.profile_id}; process restarted, open connections closed')
                    else:
                        self.report(f'App {app.id}: startup failed during failover; workload remains stopped, policy retained')
                else:
                    self.report(f'App {app.id}: both tunnels unavailable; workload remains stopped, Direct is blocked')
            except Exception as error:
                self.report(f'App {app.id}: failover could not be applied: {error}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--state', type=Path, default=Path('/etc/splitforge/state.json'))
    parser.add_argument('--interval', type=int, default=15)
    args = parser.parse_args()
    require_root()
    if args.interval < 5:
        parser.error('Interval must be at least five seconds')
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    store = StateStore(args.state)
    with store.operation():
        fd = os.open(str(store.path) + '.failover.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        stop = threading.Event()
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, lambda *_: stop.set())
        monitor = FailoverMonitor(store, stop=stop)
        while not stop.is_set():
            try:
                monitor.cycle()
            except Exception:
                logging.exception('Failover cycle failed; saved assignments retained')
            stop.wait(args.interval)
    finally:
        os.close(fd)


if __name__ == '__main__':
    main()
