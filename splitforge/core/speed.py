"""Shared profile rate limits, confined to its owned tunnel namespace."""
from __future__ import annotations

import json

from splitforge.core.netns import NetNS, require_root

MAX_RATE = 100_000_000_000  # bits/second, up to 100 Gbit/s


def validate_rate(value):
    if type(value) is not int or not 0 <= value <= MAX_RATE:
        raise ValueError('Speed must be an integer from 0 to 100000000000 bits/s (0 disables)')
    return value


def apply(profile, download=0, upload=0, *, netns=None):
    """TBF upload shaping; ingress download policing drops excess packets."""
    require_root()
    validate_rate(download)
    validate_rate(upload)
    netns = netns or NetNS()
    def command(*args):
        try:
            return netns.command(profile, *args)
        except RuntimeError as error:
            raise RuntimeError('Kernel traffic control failed; verify tc, TBF and u32/police support') from error
    device = profile.interface
    qdiscs = json.loads(command('tc', '-j', 'qdisc', 'show', 'dev', device).stdout)
    if upload:
        # A TUN's default zero-length queue cannot buffer shaped packets.
        command('ip', 'link', 'set', 'dev', device, 'txqueuelen', '1000')
        command('tc', 'qdisc', 'replace', 'dev', device, 'root', 'handle', '7f00:',
                'tbf', 'rate', f'{upload}bit', 'burst', str(max(65536, upload // 80)), 'latency', '200ms')
    elif any(q.get('handle') == '7f00:' and q.get('root') for q in qdiscs):
        command('tc', 'qdisc', 'del', 'dev', device, 'root', 'handle', '7f00:')
    if download:
        if not any(q.get('kind') in ('ingress', 'clsact') for q in qdiscs):
            command('tc', 'qdisc', 'add', 'dev', device, 'handle', 'ffff:', 'ingress')
        command('tc', 'filter', 'replace', 'dev', device, 'ingress', 'protocol', 'all',
                'pref', '49152', 'handle', '800::1', 'u32', 'match', 'u32', '0', '0', 'police',
                'rate', f'{download}bit', 'burst', str(max(65536, download // 80)),
                'conform-exceed', 'drop/ok')
    elif any(q.get('kind') in ('ingress', 'clsact') for q in qdiscs):
        filters = json.loads(command('tc', '-j', 'filter', 'show', 'dev', device, 'ingress').stdout)
        if any(f.get('pref') == 49152 for f in filters):
            command('tc', 'filter', 'del', 'dev', device, 'ingress', 'pref', '49152')


def set_limits(store, identifier, download, upload):
    """Persist offline or apply live; restore old rules if saving/applying fails."""
    require_root()
    validate_rate(download)
    validate_rate(upload)
    from splitforge.core.traffic import TrafficStore, new_row
    meter = TrafficStore(store)
    with store.operation(), meter.locked():
        profile = store.profile(identifier)
        data = meter.snapshot()
        row = data['profiles'].setdefault(profile.id, new_row())
        previous = row.get('download_bps', 0), row.get('upload_bps', 0)
        netns = NetNS()
        active = netns.exists(profile)
        try:
            if active:
                apply(profile, download, upload, netns=netns)
            row.update(download_bps=download, upload_bps=upload)
            meter.write(data)
        except Exception:
            if active:
                try:
                    apply(profile, *previous, netns=netns)
                except Exception as recovery_error:
                    # Never leave a failed rate change silently running unlimited.
                    netns.command(profile, 'ip', 'link', 'set', 'dev', profile.interface, 'down')
                    raise RuntimeError('Speed limit recovery failed; tunnel interface was disabled. Restart the profile.') from recovery_error
            raise
