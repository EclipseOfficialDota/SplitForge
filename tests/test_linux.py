"""Opt-in root Linux tests; all resources use random SplitForge IDs and clean up."""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from splitforge.core.netns import NetNS, run
from splitforge.core.runner import Runner
from splitforge.protocols.manager import ProtocolManager
from splitforge.state import AppBinding, Profile, StateStore
from helpers import TLSFixture

ENABLED = sys.platform == "linux" and os.environ.get("SPLITFORGE_INTEGRATION") == "1" and os.geteuid() == 0


@unittest.skipUnless(ENABLED, "Set SPLITFORGE_INTEGRATION=1 as root on an isolated Linux host")
class LinuxIntegrationTests(unittest.TestCase):
    def test_namespace_deny_policy_root_execution_and_main_route_preservation(self):
        before = json.loads(run(["ip", "-j", "-4", "route", "show", "table", "main"]).stdout)
        profile = Profile("integration-guard", "wireguard", {}, slot=4000)
        netns = NetNS()
        try:
            netns.create(profile)
            rules = netns.command(profile, "nft", "list", "table", "inet", "splitforge").stdout
            self.assertIn("policy drop", rules)
            self.assertNotIn("default", netns.command(profile, "ip", "-4", "route", "show").stdout)
            ipv6 = netns.command(profile, "sysctl", "-n", "net.ipv6.conf.all.disable_ipv6").stdout.strip()
            self.assertEqual(ipv6, "1")
            with tempfile.TemporaryDirectory(prefix="splitforge-root-") as directory:
                store = StateStore(Path(directory) / "state.json")
                runner = Runner(store, ProtocolManager(store))
                self.assertEqual(runner.execute(["/usr/bin/python3", "-c", "import os; assert os.geteuid()==0"],
                    profile_name="direct", user="root", cwd="/root"), 0)
        finally:
            netns.destroy(profile)
        self.assertFalse(netns.exists(profile))
        self.assertEqual(before, json.loads(run(["ip", "-j", "-4", "route", "show", "table", "main"]).stdout))

    @unittest.skipUnless(shutil.which("xray") and shutil.which("tun2socks"), "Install verified proxy cores first")
    def test_real_proxy_egress_root_binding_restart_and_cleanup(self):
        before = json.loads(run(["ip", "-j", "-4", "route", "show", "table", "main"]).stdout)
        with tempfile.TemporaryDirectory(prefix="splitforge-live-") as directory:
            base = Path(directory)
            fixture = TLSFixture(base).__enter__()
            with socket.socket() as reservation:
                reservation.bind(("127.0.0.1", 0))
                port = reservation.getsockname()[1]
            config = base / "server.json"
            config.write_text(json.dumps({"log": {"loglevel": "warning"},
                "inbounds": [{"listen": "127.0.0.1", "port": port, "protocol": "socks", "settings": {"udp": True}}],
                "outbounds": [{"protocol": "freedom", "settings": {"redirect": f"127.0.0.1:{fixture.port}"}}]}))
            log = (base / "server.log").open("w+")
            server = subprocess.Popen(["xray", "run", "-config", str(config)], stdout=log, stderr=log)
            store = StateStore(base / "state.json")
            manager = ProtocolManager(store)
            runner = Runner(store, manager)
            profile = manager.import_profile(f"socks5://127.0.0.1:{port}", name="integration-proxy")
            store.save_profile(fixture.configure(profile))
            app = AppBinding("root-sleeper", ["/usr/bin/sleep", "300"], user="root")
            store.save_app(app)
            wireguard = None
            openvpn = None
            ovpn_server = None
            ovpn_log = None
            server_interface = "wgs-" + profile.id
            try:
                for _ in range(50):
                    if server.poll() is not None:
                        self.fail("Local integration SOCKS server exited")
                    try:
                        with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                            break
                    except OSError:
                        time.sleep(0.1)
                manager.start(profile.id)
                result = manager.test(profile.id)
                self.assertTrue(result["exit_ip"])
                self.assertEqual(runner.execute(["/usr/bin/python3", "-c", "import os; assert os.geteuid()==0"],
                    profile_name=profile.id, user="root", cwd="/root"), 0)
                runner.bind(app.id, profile.id)
                self.assertTrue(runner.running(app))
                pid = run(["systemctl", "show", runner.unit(app), "--property=MainPID", "--value"]).stdout.strip()
                self.assertEqual(Path(f"/proc/{pid}/ns/net").stat().st_ino, Path("/run/netns", profile.namespace).stat().st_ino)
                # A real local WireGuard peer forwards only inside our test
                # namespace to its existing tun2socks egress; host forwarding
                # and the host main table are never changed.
                if shutil.which("wg"):
                    server_key = run(["wg", "genkey"]).stdout.strip()
                    client_key = run(["wg", "genkey"]).stdout.strip()
                    server_public = run(["wg", "pubkey"], input=server_key).stdout.strip()
                    client_public = run(["wg", "pubkey"], input=client_key).stdout.strip()
                    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as reservation:
                        reservation.bind(("127.0.0.1", 0))
                        wg_port = reservation.getsockname()[1]
                    server_conf = base / "wg-server.txt"
                    server_conf.write_text(f"[Interface]\nPrivateKey={server_key}\nListenPort={wg_port}\n[Peer]\nPublicKey={client_public}\nAllowedIPs=10.250.240.2/32\n")
                    run(["ip", "link", "add", server_interface, "type", "wireguard"])
                    run(["wg", "setconf", server_interface, str(server_conf)])
                    run(["ip", "link", "set", server_interface, "netns", profile.namespace])
                    manager.netns.command(profile, "ip", "address", "add", "10.250.240.1/24", "dev", server_interface)
                    manager.netns.command(profile, "ip", "link", "set", server_interface, "up")
                    manager.netns.command(profile, "sysctl", "-qw", "net.ipv4.ip_forward=1")
                    manager.netns.command(profile, "nft", "add", "rule", "inet", "splitforge", "forward", "iifname", server_interface,
                                          "oifname", profile.interface, "accept")
                    manager.netns.command(profile, "nft", "add", "rule", "inet", "splitforge", "forward", "iifname", profile.interface,
                                          "oifname", server_interface, "ct", "state", "established,related", "accept")
                    text = f"[Interface]\nPrivateKey={client_key}\nAddress=10.250.240.2/24\n[Peer]\nPublicKey={server_public}\nEndpoint=127.0.0.1:{wg_port}\nAllowedIPs=0.0.0.0/0\nPersistentKeepalive=15\n"
                    wireguard = store.save_profile(fixture.configure(Profile("integration-wg", "wireguard", {"text": text})))
                    manager.start(wireguard.id)
                    self.assertEqual(manager.test(wireguard.id)["exit_ip"], "192.0.2.80")
                    runner.bind(app.id, wireguard.id)
                    wg_pid = run(["systemctl", "show", runner.unit(app), "--property=MainPID", "--value"]).stdout.strip()
                    self.assertNotEqual(pid, wg_pid)
                    self.assertEqual(Path(f"/proc/{wg_pid}/ns/net").stat().st_ino, Path("/run/netns", wireguard.namespace).stat().st_ino)
                if shutil.which("openvpn"):
                    server_cert, server_key = fixture.vpn_certificate("vpn-server", "serverAuth")
                    client_cert, client_key = fixture.vpn_certificate("vpn-client", "clientAuth")
                    ovpn_interface = "ovs-" + profile.id
                    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as reservation:
                        reservation.bind(("127.0.0.1", 0))
                        ovpn_port = reservation.getsockname()[1]
                    hook = base / "server-up"
                    hook.write_text(f'#!/bin/sh\nset -eu\nip link set "$dev" netns {profile.namespace}\n'
                        f'ip -n {profile.namespace} address replace "$ifconfig_local/$ifconfig_netmask" dev "$dev"\n'
                        f'ip -n {profile.namespace} link set "$dev" up\n')
                    hook.chmod(0o700)
                    server_config = base / "server.ovpn"
                    server_config.write_text(f"local 127.0.0.1\nport {ovpn_port}\nproto udp\ndev {ovpn_interface}\ndev-type tun\n"
                        f"server 10.250.241.0 255.255.255.0\ntopology subnet\nca {fixture.cert}\ncert {server_cert}\nkey {server_key}\n"
                        f"dh none\nifconfig-noexec\nroute-noexec\nscript-security 2\nup {hook}\ndisable-dco\nverb 3\n")
                    ovpn_log = (base / "ovpn-server.log").open("w+")
                    ovpn_server = subprocess.Popen(["openvpn", "--config", str(server_config)], stdout=ovpn_log, stderr=ovpn_log)
                    deadline = time.monotonic() + 15
                    while time.monotonic() < deadline:
                        if ovpn_server.poll() is not None:
                            self.fail("OpenVPN fixture exited before becoming ready")
                        if "Initialization Sequence Completed" in (base / "ovpn-server.log").read_text():
                            break
                        time.sleep(0.1)
                    else:
                        self.fail("OpenVPN fixture did not become ready before client startup")
                    manager.netns.command(profile, "sysctl", "-qw", "net.ipv4.ip_forward=1")
                    for ingress, egress in ((ovpn_interface, profile.interface), (profile.interface, ovpn_interface)):
                        manager.netns.command(profile, "nft", "add", "rule", "inet", "splitforge", "forward", "iifname", ingress,
                                              "oifname", egress, "accept")
                    client_config = base / "client.ovpn"
                    client_config.write_text(f"client\nproto udp\nremote 127.0.0.1 {ovpn_port}\nnobind\nremote-cert-tls server\nverb 3\n"
                        f"<ca>\n{fixture.cert.read_text()}</ca>\n<cert>\n{client_cert.read_text()}</cert>\n<key>\n{client_key.read_text()}</key>\n")
                    openvpn = manager.import_profile(str(client_config), name="integration-openvpn")
                    store.save_profile(fixture.configure(openvpn))
                    manager.start(openvpn.id)
                    self.assertEqual(manager.test(openvpn.id)["exit_ip"], "192.0.2.80")
                    runner.bind(app.id, openvpn.id)
                    ovpn_pid = run(["systemctl", "show", runner.unit(app), "--property=MainPID", "--value"]).stdout.strip()
                    self.assertEqual(Path(f"/proc/{ovpn_pid}/ns/net").stat().st_ino, Path("/run/netns", openvpn.namespace).stat().st_ino)
                runner.bind(app.id, None)
                new_pid = run(["systemctl", "show", runner.unit(app), "--property=MainPID", "--value"]).stdout.strip()
                self.assertNotEqual(pid, new_pid)
                self.assertEqual(Path(f"/proc/{new_pid}/ns/net").stat().st_ino, Path("/proc/1/ns/net").stat().st_ino)
                # A host-only listener is reachable directly, but blocked from
                # the tunnel namespace even after its proxy core is stopped.
                run(["systemctl", "stop", f"splitforge-core-{profile.id}.service"])
                with socket.socket() as listener:
                    listener.bind((profile.gateway, 0))
                    listener.listen(5)
                    host_port = listener.getsockname()[1]
                    with socket.create_connection((profile.gateway, host_port), timeout=1):
                        pass
                    check = (f"import socket\ntry:\n s=socket.create_connection(({profile.gateway!r},{host_port}),timeout=1)\n"
                             "except OSError:\n pass\nelse:\n s.close(); raise SystemExit(77)\n")
                    self.assertEqual(runner.execute(["/usr/bin/python3", "-c", check], profile_name=profile.id, user="root", cwd="/"), 0)
            except Exception:
                for tested in (profile, wireguard, openvpn):
                    if tested is None:
                        continue
                    for role in ("profile", "core", "tun", "dns"):
                        details = run(["journalctl", "--no-pager", "-n", "30", "-u", f"splitforge-{role}-{tested.id}.service"], check=False)
                        print(details.stdout, file=sys.stderr)
                if (base / "ovpn-server.log").exists():
                    print((base / "ovpn-server.log").read_text()[-12000:], file=sys.stderr)
                raise
            finally:
                try:
                    if Path("/etc/systemd/system", runner.unit(app)).exists():
                        runner.remove(app.id)
                    else:
                        store.delete_app(app.id)
                finally:
                    for tunnel in (openvpn, wireguard):
                        if tunnel:
                            tunnel_unit = Path("/etc/systemd/system", f"splitforge-profile-{tunnel.id}.service")
                            if tunnel_unit.exists():
                                manager.stop(tunnel.id)
                                tunnel_unit.unlink()
                    if ovpn_server:
                        ovpn_server.terminate()
                        ovpn_server.wait(timeout=10)
                        ovpn_log.close()
                    run(["ip", "link", "delete", server_interface], check=False)
                    unit = Path("/etc/systemd/system", f"splitforge-profile-{profile.id}.service")
                    if unit.exists():
                        manager.stop(profile.id)
                        unit.unlink()
                        run(["systemctl", "daemon-reload"])
                    else:
                        manager.netns.destroy(profile)
                    server.terminate()
                    server.wait(timeout=10)
                    log.close()
                    fixture.__exit__(None, None, None)
            self.assertFalse(manager.netns.exists(profile))
        self.assertEqual(before, json.loads(run(["ip", "-j", "-4", "route", "show", "table", "main"]).stdout))
