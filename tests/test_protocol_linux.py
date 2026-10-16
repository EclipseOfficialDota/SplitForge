"""Actual loopback Xray transports, followed by verified HTTPS and encrypted DNS."""
import base64
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

from helpers import TLSFixture
from splitforge.core.netns import run
from splitforge.protocols.manager import ProtocolManager
from splitforge.state import StateStore


@unittest.skipUnless(sys.platform == "linux" and os.environ.get("SPLITFORGE_INTEGRATION") == "1"
    and os.geteuid() == 0 and shutil.which("xray") and shutil.which("tun2socks"), "Opt-in Linux protocol integration")
class XrayIntegrationTests(unittest.TestCase):
    def test_vless_vmess_shadowsocks_and_verified_tls_trojan(self):
        before = json.loads(run(["ip", "-j", "-4", "route", "show", "table", "main"]).stdout)
        identity = "2b1f7aec-8080-4e54-a4ee-498bc48674fd"
        with tempfile.TemporaryDirectory(prefix="splitforge-protocols-") as directory:
            base = Path(directory)
            with TLSFixture(base) as fixture:
                store = StateStore(base / "state.json")
                manager = ProtocolManager(store)
                for protocol in ("vless", "vmess", "shadowsocks", "trojan"):
                    with self.subTest(protocol=protocol):
                        with socket.socket() as reservation:
                            reservation.bind(("127.0.0.1", 0))
                            port = reservation.getsockname()[1]
                        stream = {}
                        if protocol == "trojan":
                            settings = {"clients": [{"password": "test-only-password"}]}
                            uri = f"trojan://test-only-password@127.0.0.1:{port}?sni=dns.splitforge.test"
                            stream = {"streamSettings": {"security": "tls", "tlsSettings": {"certificates": [
                                {"certificateFile": str(fixture.cert), "keyFile": str(base / "fixture-key.pem")}]}}}
                        elif protocol == "vless":
                            settings = {"clients": [{"id": identity}], "decryption": "none"}
                            uri = f"vless://{identity}@127.0.0.1:{port}?security=none"
                        elif protocol == "vmess":
                            settings = {"clients": [{"id": identity, "alterId": 0}]}
                            uri = "vmess://" + base64.b64encode(json.dumps({"add": "127.0.0.1", "port": port, "id": identity}).encode()).decode()
                        else:
                            settings = {"method": "aes-256-gcm", "password": "test-only-password", "network": "tcp"}
                            credentials = base64.urlsafe_b64encode(b"aes-256-gcm:test-only-password").decode()
                            uri = f"ss://{credentials}@127.0.0.1:{port}"
                        path = base / f"{protocol}.json"
                        path.write_text(json.dumps({"log": {"loglevel": "warning"}, "inbounds": [{"listen": "127.0.0.1",
                            "port": port, "protocol": protocol, "settings": settings, **stream}],
                            "outbounds": [{"protocol": "freedom", "settings": {"redirect": f"127.0.0.1:{fixture.port}"}}]}))
                        with (base / f"{protocol}.log").open("w+") as log:
                            server = subprocess.Popen(["xray", "run", "-config", str(path)], stdout=log, stderr=log)
                            profile = manager.import_profile(uri, name=f"integration-{protocol}")
                            if protocol == "trojan":
                                # Official Xray TLS CertificateObject usage=verify
                                # adds our fixture CA without disabling verification.
                                profile.config["outbound"]["streamSettings"]["tlsSettings"]["certificates"] = [
                                    {"certificateFile": str(fixture.cert), "usage": "verify"}]
                            store.save_profile(fixture.configure(profile))
                            try:
                                for _ in range(40):
                                    if server.poll() is not None:
                                        log.seek(0)
                                        self.fail(log.read())
                                    try:
                                        with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                                            break
                                    except OSError:
                                        time.sleep(0.1)
                                manager.start(profile.id)
                                self.assertEqual(manager.test(profile.id)["exit_ip"], "192.0.2.80")
                            finally:
                                unit = Path("/etc/systemd/system", f"splitforge-profile-{profile.id}.service")
                                if unit.exists():
                                    manager.stop(profile.id)
                                    unit.unlink()
                                    run(["systemctl", "daemon-reload"])
                                else:
                                    manager.netns.destroy(profile)
                                server.terminate()
                                server.wait(timeout=10)
        self.assertEqual(before, json.loads(run(["ip", "-j", "-4", "route", "show", "table", "main"]).stdout))
