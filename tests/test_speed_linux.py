"""Actual kernel rate enforcement without touching host addresses or routes."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from splitforge.core.netns import NetNS, run
from splitforge.core.speed import apply, set_limits
from splitforge.core.traffic import TrafficStore
from splitforge.state import Profile, StateStore


@unittest.skipUnless(os.environ.get('SPLITFORGE_INTEGRATION') == '1' and os.geteuid() == 0,
                     'Opt-in root network namespace rate enforcement')
class SpeedLinuxTests(unittest.TestCase):
    def test_live_limits_offline_persistence_recovery_and_actual_rates(self):
        before = run(['ip', '-j', '-4', 'route', 'show', 'table', 'main']).stdout
        with tempfile.TemporaryDirectory(prefix='splitforge-speed-') as directory:
            store = StateStore(Path(directory) / 'state.json')
            profile = Profile('limited', 'socks5', {})
            store.save_profile(profile)
            peer = 'sf-speed-' + profile.id
            netns = NetNS()
            meter = TrafficStore(store)
            set_limits(store, profile.id, 2000000, 1000000)
            self.assertEqual(meter.snapshot()['profiles'][profile.id]['download_bps'], 2000000)
            try:
                run(['ip', 'netns', 'add', profile.namespace])
                run(['ip', 'netns', 'add', peer])
                netns.command(profile, 'ip', 'link', 'add', profile.interface, 'type', 'veth', 'peer', 'name', 'speed-peer')
                netns.command(profile, 'ip', 'link', 'set', 'speed-peer', 'netns', peer)
                netns.command(profile, 'ip', 'addr', 'add', '198.18.0.1/30', 'dev', profile.interface)
                netns.command(profile, 'ip', 'link', 'set', profile.interface, 'up')
                run(['ip', 'netns', 'exec', peer, 'ip', 'addr', 'add', '198.18.0.2/30', 'dev', 'speed-peer'])
                run(['ip', 'netns', 'exec', peer, 'ip', 'link', 'set', 'speed-peer', 'up'])
                set_limits(store, profile.id, 2000000, 1000000)
                qdiscs = json.loads(netns.command(profile, 'tc', '-j', 'qdisc', 'show', 'dev', profile.interface).stdout)
                self.assertTrue(any(q['kind'] == 'tbf' for q in qdiscs))
                # TCP receiver measures actual arrival time, not buffered sendall time.
                def transfer(receiver_namespace, address, sender_namespace):
                    server = subprocess.Popen(['ip', 'netns', 'exec', receiver_namespace, sys.executable, '-u', '-c',
                        'import socket,time,json; s=socket.socket(); s.bind(("'+address+'",0)); s.listen(); '
                        'print(s.getsockname()[1],flush=True); c,_=s.accept(); c.settimeout(25); '
                        'start=time.monotonic(); total=0\n'
                        'while total<524288:\n'
                        ' chunk=c.recv(65536)\n'
                        ' if not chunk: raise RuntimeError("Incomplete transfer")\n'
                        ' total+=len(chunk)\n'
                        'print(json.dumps([total,time.monotonic()-start]),flush=True)'],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    try:
                        port = int(server.stdout.readline())
                        run(['ip', 'netns', 'exec', sender_namespace, sys.executable, '-c',
                             'import socket; s=socket.create_connection(("'+address+'",'+str(port)+'),timeout=25); '
                             's.sendall(b"x"*524288); s.shutdown(socket.SHUT_WR); s.close()'], timeout=30)
                        output, errors = server.communicate(timeout=30)
                        self.assertEqual(server.returncode, 0, errors)
                        size, elapsed = json.loads(output)
                        self.assertEqual(size, 524288)
                        return elapsed
                    finally:
                        if server.poll() is None:
                            server.kill()
                            server.communicate()
                upload_seconds = transfer(peer, '198.18.0.2', profile.namespace)
                download_seconds = transfer(profile.namespace, '198.18.0.1', peer)
                self.assertGreater(upload_seconds, 2.5, '1 Mbit/s upload must be shaped, not only saved')
                self.assertGreater(download_seconds, 0.8, '2 Mbit/s download must be policed')
                original = apply
                attempts = []
                def fail_once(*args, **kwargs):
                    attempts.append(1)
                    if len(attempts) == 1:
                        raise RuntimeError('Injected tc failure')
                    return original(*args, **kwargs)
                with patch('splitforge.core.speed.apply', side_effect=fail_once), self.assertRaisesRegex(RuntimeError, 'Injected'):
                    set_limits(store, profile.id, 3000000, 3000000)
                self.assertEqual(meter.snapshot()['profiles'][profile.id]['upload_bps'], 1000000)
                with patch('splitforge.core.speed.apply', side_effect=RuntimeError('Persistent tc failure')), self.assertRaisesRegex(RuntimeError, 'interface was disabled'):
                    set_limits(store, profile.id, 3000000, 3000000)
                link = json.loads(netns.command(profile, 'ip', '-j', 'link', 'show', 'dev', profile.interface).stdout)[0]
                self.assertNotIn('UP', link['flags'])
                netns.command(profile, 'ip', 'link', 'set', profile.interface, 'up')
                set_limits(store, profile.id, 0, 0)
                qdiscs = json.loads(netns.command(profile, 'tc', '-j', 'qdisc', 'show', 'dev', profile.interface).stdout)
                self.assertFalse(any(q.get('handle') == '7f00:' for q in qdiscs))
                filters = json.loads(netns.command(profile, 'tc', '-j', 'filter', 'show', 'dev', profile.interface, 'ingress').stdout)
                self.assertFalse(any(f.get('pref') == 49152 for f in filters))
            finally:
                run(['ip', 'netns', 'del', profile.namespace], check=False)
                run(['ip', 'netns', 'del', peer], check=False)
            self.assertEqual(before, run(['ip', '-j', '-4', 'route', 'show', 'table', 'main']).stdout)
