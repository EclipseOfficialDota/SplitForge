"""Independent systemd cgroup IP counters, tunnel counters and sampled budgets."""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import logging
import math
import os
import re
import signal
import stat
import subprocess
import sys
import threading
import time
from pathlib import Path

from splitforge.core.netns import atomic_secret, require_root, run, unit_word
from splitforge.state import StateStore, checked_id

MARKER = '# SplitForge traffic monitor\n'
HISTORY = 120
MAX_COUNTER = 2**64 - 1  # systemd uses UINT64_MAX for unavailable accounting.


def empty_data():
    return {'version': 1, 'apps': {}, 'profiles': {}, 'events': [], 'updated': 0}


def validate_data(data):
    if not isinstance(data, dict) or data.get('version') != 1:
        raise ValueError('Unsupported traffic state; refusing to bypass saved quotas')
    for kind in ('apps', 'profiles'):
        if not isinstance(data.get(kind), dict):
            raise ValueError('Invalid traffic records')
        for identifier, row in data[kind].items():
            checked_id(identifier)
            if not isinstance(row, dict):
                raise ValueError('Invalid traffic record')
            for name in ('rx', 'tx', 'baseline'):
                if type(row.get(name)) is not int or row[name] < 0:
                    raise ValueError('Invalid traffic byte counter')
            if row['baseline'] > row['rx'] + row['tx']:
                raise ValueError('Invalid quota baseline')
            quota = row.get('quota')
            from splitforge.core.speed import validate_rate
            for field in ('download_bps', 'upload_bps'):
                validate_rate(row.get(field, 0))
            if quota is not None and (type(quota) is not int or not 1 <= quota < 2**63):
                raise ValueError('Invalid traffic quota')
            if type(row.get('warn_percent')) is not int or not 1 <= row['warn_percent'] <= 99:
                raise ValueError('Invalid traffic warning threshold')
            if not isinstance(row.get('epochs'), dict) or len(row['epochs']) > 128:
                raise ValueError('Invalid traffic invocation records')
            for epoch, pair in row['epochs'].items():
                if not isinstance(epoch, str) or len(epoch) > 160 or not isinstance(pair, list) or len(pair) != 2:
                    raise ValueError('Invalid traffic invocation counter')
                if any(type(value) is not int or not 0 <= value < MAX_COUNTER for value in pair):
                    raise ValueError('Invalid raw traffic counter')
            if not isinstance(row.get('history'), list) or len(row['history']) > HISTORY:
                raise ValueError('Invalid traffic history')
            for point in row['history']:
                if (not isinstance(point, list) or len(point) != 3
                        or type(point[0]) not in (int, float) or not math.isfinite(point[0]) or point[0] < 0
                        or any(type(value) is not int or value < 0 for value in point[1:])):
                    raise ValueError('Invalid traffic history point')
            for key in ('blocked', 'warned', 'available', 'supported'):
                if type(row.get(key)) is not bool:
                    raise ValueError('Invalid traffic status')
            if (type(row.get('updated')) not in (int, float) or not math.isfinite(row['updated'])
                    or row['updated'] < 0 or not isinstance(row.get('error'), str) or len(row['error']) > 300):
                raise ValueError('Invalid traffic sample status')
    if not isinstance(data.get('events'), list) or len(data['events']) > 50:
        raise ValueError('Invalid traffic event history')
    if type(data.get('updated')) not in (int, float) or not math.isfinite(data['updated']) or data['updated'] < 0:
        raise ValueError('Invalid traffic update time')
    for event in data['events']:
        if (not isinstance(event, dict) or event.get('kind') not in ('apps', 'profiles')
                or event.get('level') not in ('warning', 'blocked')
                or event.get('reason') not in ('quota', 'accounting unavailable', 'quota warning threshold')
                        or type(event.get('time')) not in (int, float) or not math.isfinite(event['time']) or event['time'] < 0):
            raise ValueError('Invalid traffic event')
        checked_id(event.get('id', ''))
    return data


def new_row():
    return {'rx': 0, 'tx': 0, 'baseline': 0, 'quota': None, 'warn_percent': 80,
            'epochs': {}, 'history': [], 'blocked': False, 'warned': False,
            'available': False, 'supported': False, 'error': '', 'updated': 0}


def update_row(row, sample, timestamp):
    """Merge monotonic counters per invocation, including out-of-order finals."""
    epoch, rx, tx = sample
    if not isinstance(epoch, str) or not epoch or len(epoch) > 160:
        raise ValueError('Invalid counter identity')
    if any(type(value) is not int or not 0 <= value < MAX_COUNTER for value in (rx, tx)):
        raise ValueError('Independent traffic accounting is unavailable')
    previous = row['epochs'].get(epoch, [0, 0])
    # A stale sample must not rewind a counter or make the next sample double-count.
    observed = [max(previous[0], rx), max(previous[1], tx)]
    row['rx'] += observed[0] - previous[0]
    row['tx'] += observed[1] - previous[1]
    row['epochs'][epoch] = observed
    while len(row['epochs']) > 128:
        del row['epochs'][next(iter(row['epochs']))]
    row.update(available=True, supported=True, error='', updated=timestamp)
    point = [timestamp, row['rx'], row['tx']]
    if row['history'] and timestamp - row['history'][-1][0] < 1:
        row['history'][-1] = point
    else:
        row['history'].append(point)
        del row['history'][:-HISTORY]
    return row


def used(row):
    return row['rx'] + row['tx'] - row['baseline']


def unit_name(store):
    digest = hashlib.sha256(str(store.path.resolve()).encode()).hexdigest()[:12]
    return f'splitforge-traffic-{digest}.service'


def ensure_service(store):
    require_root()
    path = Path('/etc/systemd/system', unit_name(store))
    if path.exists() and not path.read_text().startswith(MARKER):
        raise ValueError('Refusing to replace an unrelated traffic service')
    command = [sys.executable, '-m', 'splitforge.core.traffic', '--state', str(store.path.resolve()), 'watch']
    text = MARKER + f'''[Unit]
Description=SplitForge independent traffic accounting and budgets
After=network-online.target
[Service]
Type=simple
User=root
ExecStart={' '.join(unit_word(word) for word in command)}
Restart=on-failure
RestartSec=5
UMask=0077
KillMode=mixed
TimeoutStopSec=3min
[Install]
WantedBy=multi-user.target
'''
    if not path.exists() or path.read_text() != text:
        atomic_secret(path, text, 0o644)
        run(['systemctl', 'daemon-reload'])
    run(['systemctl', 'enable', '--now', path.name])


def stop_service(store):
    run(['systemctl', 'stop', unit_name(store)], check=False, timeout=190)
    if run(['systemctl', 'is-active', '--quiet', unit_name(store)], check=False).returncode == 0:
        raise RuntimeError('Traffic monitor did not stop; maintenance was cancelled')


def cleanup_if_unused(store):
    snapshot = store.snapshot()
    if snapshot['apps'] or snapshot['profiles'] or snapshot['users']:
        return
    path = Path('/etc/systemd/system', unit_name(store))
    if path.is_file() and path.read_text().startswith(MARKER):
        stop_service(store)
        run(['systemctl', 'disable', path.name])
        path.unlink()
        run(['systemctl', 'daemon-reload'])
    from splitforge.core.failover import MARKER as FAILOVER_MARKER, unit_name as failover_unit_name
    path = Path('/etc/systemd/system', failover_unit_name(store))
    if path.is_file() and path.read_text().startswith(FAILOVER_MARKER):
        run(['systemctl', 'disable', '--now', path.name], timeout=310)
        path.unlink()
        run(['systemctl', 'daemon-reload'])


class TrafficStore:
    def __init__(self, store):
        self.store = store
        self.path = Path(str(store.path) + '.traffic.json')

    def snapshot(self):
        if self.path.is_symlink():
            raise ValueError('Traffic state must not be a symlink')
        if not self.path.exists():
            return empty_data()
        info = self.path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o022 or info.st_size > 64 * 1024 * 1024:
            raise ValueError('Traffic state ownership, permissions or size is invalid')
        return validate_data(json.loads(self.path.read_text()))

    @contextlib.contextmanager
    def locked(self):
        import fcntl
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.path.parent.is_symlink():
            raise ValueError('Traffic directory must not be a symlink')
        descriptor = os.open(str(self.path) + '.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    def write(self, data):
        atomic_secret(self.path, json.dumps(validate_data(data), separators=(',', ':')))

    def guard(self, kind, identifier, *, monitor=False):
        row = self.snapshot()[kind].get(checked_id(identifier))
        if row and row['quota'] is not None and (row['blocked'] or used(row) >= row['quota']):
            raise RuntimeError('Traffic quota blocks this workload; reset its budget or increase the limit')
        if row and row['quota'] is not None and monitor and run(
                ['systemctl', 'is-active', '--quiet', unit_name(self.store)], check=False).returncode != 0:
            raise RuntimeError('Traffic monitor is unavailable; quota-protected startup was blocked')

    @staticmethod
    def app_sample(runner, app):
        properties = 'IPAccounting,IPIngressBytes,IPEgressBytes,InvocationID,ActiveState'
        response = run(['systemctl', 'show', runner.unit(app), f'--property={properties}'], check=False, timeout=5)
        values = dict(line.split('=', 1) for line in response.stdout.splitlines() if '=' in line)
        invocation = values.get('InvocationID', '')
        if values.get('IPAccounting') != 'yes':
            raise ValueError('Reapply the app route to enable independent kernel IP accounting')
        if values.get('ActiveState') in ('inactive', 'failed'):
            raise ValueError('Application is stopped; its last counter reading is retained')
        if not re.fullmatch('[0-9a-f]{32}', invocation):
            raise ValueError('Start the application to collect independent counters')
        rx, tx = int(values.get('IPIngressBytes', str(MAX_COUNTER))), int(values.get('IPEgressBytes', str(MAX_COUNTER)))
        if rx == MAX_COUNTER or tx == MAX_COUNTER:
            raise ValueError('Kernel/systemd independent IP accounting is unavailable')
        boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        return (boot + ':' + invocation, rx, tx)

    @staticmethod
    def profile_sample(manager, profile):
        path = Path('/run/netns', profile.namespace)
        if not path.exists():
            raise ValueError('Start the tunnel to collect interface counters')
        response = manager.netns.command(profile, 'ip', '-j', '-s', 'link', 'show', 'dev', profile.interface, check=False, timeout=5)
        if response.returncode:
            raise ValueError('Tunnel interface accounting is unavailable')
        link = json.loads(response.stdout)[0]
        stats = link.get('stats64', link.get('stats', {}))
        boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        activation = Path('/run/splitforge', profile.id, 'traffic.id')
        if not activation.is_file() or not re.fullmatch('[0-9a-f]{32}', activation.read_text()):
            raise ValueError('Restart this tunnel to enable persistent activation accounting')
        identity = f'{boot}:{activation.read_text()}:{path.stat().st_ino}:{link["ifindex"]}'
        return identity, stats['rx']['bytes'], stats['tx']['bytes']

    def record(self, kind, identifier, sample, *, error='', active=False):
        checked_id(identifier)
        timestamp = time.time()
        with self.locked():
            data = self.snapshot()
            row = data[kind].setdefault(identifier, new_row())
            if sample is not None:
                update_row(row, sample, timestamp)
            else:
                row.update(available=False, error=str(error)[:300])
            if row['quota'] is not None:
                exhausted = used(row) >= row['quota']
                uncounted = active and sample is None
                if (exhausted or uncounted) and not row['blocked']:
                    row['blocked'] = True
                    data['events'].append({'time': timestamp, 'kind': kind, 'id': identifier,
                        'level': 'blocked', 'reason': 'quota' if exhausted else 'accounting unavailable'})
                if used(row) * 100 >= row['quota'] * row['warn_percent'] and not row['warned']:
                    row['warned'] = True
                    data['events'].append({'time': timestamp, 'kind': kind, 'id': identifier,
                                           'level': 'warning', 'reason': 'quota warning threshold'})
            del data['events'][:-50]
            data['updated'] = timestamp
            self.write(data)
            return row

    def record_app(self, runner, app, *, final=False):
        try:
            sample = self.app_sample(runner, app)
            return self.record('apps', app.id, sample, active=not final)
        except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
            return self.record('apps', app.id, None, error=str(error), active=not final and runner.running(app))

    def set_quota(self, kind, identifier, limit, *, warning=80, reset=False):
        require_root()
        if kind not in ('apps', 'profiles'):
            raise ValueError('Choose apps or profiles')
        checked_id(identifier)
        if identifier not in self.store.snapshot()[kind]:
            raise ValueError('Unknown traffic target')
        if limit is not None and (type(limit) is not int or not 1 <= limit < 2**63):
            raise ValueError('Quota must be a positive byte count or disabled')
        if type(warning) is not int or not 1 <= warning <= 99 or type(reset) is not bool:
            raise ValueError('Warning must be 1–99 percent and reset must be boolean')
        from splitforge.core.runner import Runner
        from splitforge.protocols.manager import ProtocolManager
        manager = ProtocolManager(self.store)
        if kind == 'apps':
            self.record_app(Runner(self.store, manager), self.store.app(identifier))
        else:
            profile = self.store.profile(identifier)
            try:
                self.record(kind, identifier, self.profile_sample(manager, profile))
            except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
                self.record(kind, identifier, None, error=str(error), active=manager.netns.exists(profile))
        if kind == 'apps' and limit is not None and not self.snapshot()[kind].get(identifier, new_row())['supported']:
            raise ValueError('Start this target and verify independent counters before setting a quota')
        ensure_service(self.store)
        with self.locked():
            data = self.snapshot()
            row = data[kind].setdefault(identifier, new_row())
            if kind == 'apps' and limit is not None and not row['supported']:
                raise ValueError('Start this target and verify independent counters before setting a quota')
            if reset or row['quota'] is None:
                row['baseline'] = row['rx'] + row['tx']
            row['quota'], row['warn_percent'] = limit, warning
            row['blocked'] = limit is not None and used(row) >= limit
            row['warned'] = limit is not None and used(row) * 100 >= limit * warning
            self.write(data)


class TrafficMonitor:
    def __init__(self, store, manager, runner):
        self.store, self.manager, self.runner = store, manager, runner
        self.traffic = TrafficStore(store)

    def cycle(self):
        try:
            previous = self.traffic.snapshot()
        except Exception:
            # An unreadable quota registry must not turn configured limits off.
            for app in self.store.apps():
                try:
                    self.runner.stop(app.id)
                except Exception:
                    logging.exception('Could not stop workload after traffic-state failure')
            for profile in self.store.profiles():
                try:
                    self.manager.stop(profile.id)
                except Exception:
                    logging.exception('Could not stop tunnel after traffic-state failure')
            raise
        for app in self.store.apps():
            try:
                row = self.traffic.record_app(self.runner, app)
                if row['blocked'] and app.enabled:
                    self.runner.stop(app.id)
            except Exception:
                if previous['apps'].get(app.id, {}).get('quota') is not None:
                    try:
                        self.runner.stop(app.id)
                    except Exception:
                        logging.exception('Could not stop quota-protected workload after persistence failure')
                logging.exception('Application traffic sample failed')
        for profile in self.store.profiles():
            try:
                sample = self.traffic.profile_sample(self.manager, profile)
                row = self.traffic.record('profiles', profile.id, sample, active=True)
            except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
                active = self.manager.netns.exists(profile)
                try:
                    row = self.traffic.record('profiles', profile.id, None, error=str(error), active=active)
                except Exception:
                    if previous['profiles'].get(profile.id, {}).get('quota') is not None:
                        self.manager.stop(profile.id)
                    logging.exception('Tunnel traffic persistence failed')
                    continue
            if row['blocked'] and self.manager.netns.exists(profile):
                self.manager.stop(profile.id)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--state', type=Path, default=Path('/etc/splitforge/state.json'))
    parser.add_argument('action', choices=['watch', 'check', 'final'])
    parser.add_argument('--app')
    parser.add_argument('--profile')
    parser.add_argument('--interval', type=int, default=5)
    args = parser.parse_args()
    require_root()
    from splitforge.core.runner import Runner
    from splitforge.protocols.manager import ProtocolManager
    store = StateStore(args.state)
    traffic = TrafficStore(store)
    manager = ProtocolManager(store)
    runner = Runner(store, manager)
    if args.action == 'check':
        if args.app is None:
            parser.error('--app is required for an application check')
        try:
            binding = store.app(checked_id(args.app))
            traffic.guard('apps', binding.id, monitor=True)
            row = traffic.snapshot()['apps'].get(binding.id)
            if row and row['quota'] is not None:
                try:
                    traffic.app_sample(runner, binding)
                except Exception as error:
                    traffic.record('apps', binding.id, None, error=str(error), active=True)
                    raise
            if args.profile:
                profile = store.profile(checked_id(args.profile))
                traffic.guard('profiles', profile.id, monitor=True)
        except Exception as error:
            print(str(error), file=sys.stderr)
            raise SystemExit(1) from None
        return
    if args.action == 'final':
        if args.app is None:
            parser.error('--app is required for a final application sample')
        traffic.record_app(runner, store.app(checked_id(args.app)), final=True)
        return
    if args.interval < 1:
        parser.error('Interval must be positive')
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    monitor = TrafficMonitor(store, manager, runner)
    while not stop.is_set():
        try:
            monitor.cycle()
        except Exception:
            logging.exception('Traffic sample failed; saved quotas were retained')
        stop.wait(args.interval)


if __name__ == '__main__':
    main()
