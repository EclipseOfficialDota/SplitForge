"""Real managed bond namespace, root workload, DNS/HTTPS and member loss."""
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from helpers import TLSFixture
from splitforge.core.netns import run
from splitforge.core.runner import Runner
from splitforge.protocols.manager import ProtocolManager
from splitforge.state import AppBinding, StateStore


@unittest.skipUnless(os.environ.get('SPLITFORGE_INTEGRATION') == '1' and os.geteuid() == 0,
                     'Opt-in root/systemd aggregation integration')
class BondLinuxTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('xray') and shutil.which('tun2socks'), 'Proxy cores required')
    def test_managed_root_workload_dns_egress_member_loss_and_reference_cleanup(self):
        self.exercise(False)

    @unittest.skipUnless(all(shutil.which(binary) for binary in ('xray', 'tun2socks', 'dnstt-client', 'dnstt-server', 'noizdns-client', 'noizdns-server', 'slipstream-client', 'slipstream-server')), 'Actual mixed DNS tunnel clients and servers required')
    def test_real_dnstt_noizdns_slipstream_paths_share_one_managed_output(self):
        self.exercise(True)

    def exercise(self, mixed):
        before = run(['ip', '-j', '-4', 'route', 'show', 'table', 'main']).stdout
        with tempfile.TemporaryDirectory(prefix='splitforge-bond-') as directory:
            base = Path(directory)
            with TLSFixture(base) as fixture:
                def port():
                    with socket.socket() as reservation:
                        reservation.bind(('127.0.0.1', 0))
                        return reservation.getsockname()[1]
                proxy_port, relay_port = port(), port()
                config = base / 'server.json'
                config.write_text(json.dumps({'log': {'loglevel': 'warning'}, 'inbounds': [
                    {'listen': '127.0.0.1', 'port': proxy_port, 'protocol': 'socks', 'settings': {'udp': True}}],
                    'outbounds': [{'tag': 'normal', 'protocol': 'freedom'},
                                  {'tag': 'fixture', 'protocol': 'freedom', 'settings': {'redirect': f'127.0.0.1:{fixture.port}'}}],
                    'routing': {'rules': [{'type': 'field', 'ip': ['192.0.2.0/24'], 'outboundTag': 'fixture'}]}}))
                proxy = subprocess.Popen(['xray', 'run', '-config', str(config)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                relay_config = base / 'relay.json'
                token = secrets.token_hex(32)
                relay_config.write_text(json.dumps({'token': token, 'port': relay_port, 'fixture_port': fixture.port}))
                relay_code = '''import asyncio,json,sys
from splitforge.core.bond import Relay,Mux
config=json.load(open(sys.argv[1]))
async def target(self,payload):
 host,port=json.loads(payload)
 if host not in ('192.0.2.53','192.0.2.80'): raise ValueError('Unexpected lab target')
 return await asyncio.open_connection('127.0.0.1',config['fixture_port'])
Mux.target=target
async def main():
 relay=Relay(config['token'])
 server=await asyncio.start_server(relay.accept,'127.0.0.1',config['port'])
 async with server: await server.serve_forever()
asyncio.run(main())
'''
                relay = subprocess.Popen([sys.executable, '-c', relay_code, str(relay_config)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                store = StateStore(base / 'state.json')
                manager, members, bond = ProtocolManager(store), [], None
                runner = Runner(store, manager)
                transports = []
                try:
                    for number in (proxy_port, relay_port):
                        deadline = time.monotonic() + 10
                        while time.monotonic() < deadline:
                            try:
                                with socket.create_connection(('127.0.0.1', number), timeout=.1):
                                    break
                            except OSError:
                                time.sleep(.05)
                        else:
                            self.fail('Local aggregation fixture failed to start')
                    for index in range(3):
                        if not mixed:
                            member = manager.import_profile(f'socks5://127.0.0.1:{proxy_port}', name=f'bond-path-{index}')
                        else:
                            protocol = ('dnstt', 'noizdns', 'slipstream')[index]
                            domain, dns_port = f'{protocol}.splitforge.test', port()
                            if protocol in ('dnstt', 'noizdns'):
                                binary = protocol + '-server'
                                private, public = base / f'{protocol}.key', base / f'{protocol}.pub'
                                run([binary, '-gen-key', '-privkey-file', str(private), '-pubkey-file', str(public)])
                                argv = ([binary, '-udp', f'127.0.0.1:{dns_port}', '-privkey-file', str(private), domain, f'127.0.0.1:{proxy_port}']
                                        if protocol == 'dnstt' else [binary, '-privkey-file', str(private), domain, f'127.0.0.1:{dns_port}', f'127.0.0.1:{proxy_port}'])
                                member = manager.dns_tunnel(protocol, protocol, domain, f'udp://127.0.0.1:{dns_port}', public_key=public.read_text().strip())
                            else:
                                private, certificate = base / 'slip.key', base / 'slip.pem'
                                run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1', '-subj', f'/CN={domain}',
                                     '-addext', f'subjectAltName=DNS:{domain}', '-keyout', str(private), '-out', str(certificate)])
                                argv = ['slipstream-server', '--dns-listen-host', '127.0.0.1', '--dns-listen-port', str(dns_port),
                                        '--target-address', f'127.0.0.1:{proxy_port}', '--domain', domain, '--cert', str(certificate), '--key', str(private)]
                                member = manager.dns_tunnel(protocol, protocol, domain, f'127.0.0.1:{dns_port}', certificate=str(certificate))
                            log = base / f'{protocol}.log'
                            with log.open('wb') as output:
                                transports.append(subprocess.Popen(argv, stdout=output, stderr=output))
                        store.save_profile(fixture.configure(member))
                        members.append(member)
                    bond = manager.bond('combined', [member.id for member in members], '127.0.0.1', relay_port, token)
                    store.save_profile(fixture.configure(bond))
                    manager.start(bond.id)
                    self.assertEqual(manager.test(bond.id)['exit_ip'], '192.0.2.80')
                    deadline = time.monotonic() + 10
                    while time.monotonic() < deadline and manager.status(bond.id).get('bond', {}).get('paths', 0) != 3:
                        time.sleep(.2)
                    self.assertEqual(manager.status(bond.id)['bond']['paths'], 3)
                    with self.assertRaisesRegex(ValueError, 'aggregation group'):
                        manager.remove(members[0].id)
                    app = AppBinding('bond-root-worker', [sys.executable, '-c', 'import time; time.sleep(120)'], user='root')
                    store.save_app(app)
                    runner.bind(app.id, bond.id)
                    pid = run(['systemctl', 'show', runner.unit(app), '-p', 'MainPID', '--value']).stdout.strip()
                    self.assertEqual(Path(f'/proc/{pid}/ns/net').stat().st_ino, Path('/run/netns', bond.namespace).stat().st_ino)
                    self.assertEqual(runner.test(app.id)['exit_ip'], '192.0.2.80')
                    manager.stop(members[0].id)
                    self.assertEqual(manager.test(bond.id)['exit_ip'], '192.0.2.80')
                    self.assertTrue(runner.running(app))
                    self.assertEqual(before, run(['ip', '-j', '-4', 'route', 'show', 'table', 'main']).stdout)
                finally:
                    for app in store.apps():
                        runner.remove(app.id)
                    if bond:
                        manager.remove(bond.id)
                    for member in members:
                        manager.remove(member.id)
                    for process in (*transports, relay, proxy):
                        process.terminate()
                        process.wait(timeout=10)
