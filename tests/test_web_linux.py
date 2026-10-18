"""Opt-in real HTTP → state → systemd workload integration."""
import http.client
import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path

from splitforge.core.netns import run
from splitforge.web.server import Panel, PanelServer


@unittest.skipUnless(sys.platform == "linux" and os.environ.get("SPLITFORGE_INTEGRATION") == "1"
                     and os.geteuid() == 0, "Opt-in root Linux HTTP integration")
class WebLinuxTests(unittest.TestCase):
    def test_authenticated_profile_management_and_real_root_workload_lifecycle(self):
        before = json.loads(run(["ip", "-j", "-4", "route", "show", "table", "main"]).stdout)
        with tempfile.TemporaryDirectory(prefix="splitforge-web-") as directory:
            panel = Panel(Path(directory) / "state.json")
            token = "integration-token-with-at-least-thirty-two-characters"
            with PanelServer(("127.0.0.1", 0), panel, token) as server:
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                cookie, csrf = "", ""

                def request(method, path, data=None):
                    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=15)
                    headers = {"Cookie": cookie, "X-SplitForge-CSRF": csrf}
                    body = None
                    if data is not None:
                        body = json.dumps(data)
                        headers["Content-Type"] = "application/json"
                    connection.request(method, path, body=body, headers=headers)
                    response = connection.getresponse()
                    result = json.loads(response.read())
                    returned = dict(response.getheaders())
                    status = response.status
                    connection.close()
                    return status, result, returned

                def action(data):
                    status, response, _ = request("POST", "/api/action", data)
                    self.assertEqual(status, 202, response)
                    panel.worker.join(timeout=40)
                    self.assertFalse(panel.worker.is_alive())
                    self.assertEqual(panel.jobs[0]["state"], "success", panel.jobs[0])

                try:
                    status, login, headers = request("POST", "/api/login", {"token": token})
                    self.assertEqual(status, 200)
                    cookie, csrf = headers["Set-Cookie"].split(";", 1)[0], login["csrf"]
                    action({"action": "profile.import", "name": "web-socks", "source": "socks5://test:private@127.0.0.1:1081"})
                    profile = panel.store.profiles()[0]
                    action({"action": "profile.import", "id": profile.id, "name": "web-socks", "source": "socks5://127.0.0.1:1082"})
                    self.assertEqual(panel.store.profiles()[0].id, profile.id)
                    action({"action": "profile.dns", "id": profile.id, "url": "https://dns.example.com/dns-query", "bootstrap": "192.0.2.53"})
                    action({"action": "app.add", "name": "web-root-sleeper", "command": "/usr/bin/sleep 60", "user": "root", "cwd": "/"})
                    app = panel.store.apps()[0]
                    action({"action": "app.bind", "id": app.id, "profile_id": ""})
                    self.assertTrue(panel.runner.running(app))
                    pid = run(["systemctl", "show", panel.runner.unit(app), "--property=MainPID", "--value"]).stdout.strip()
                    self.assertEqual(Path(f"/proc/{pid}/ns/net").stat().st_ino, Path("/proc/1/ns/net").stat().st_ino)
                    status, snapshot, _ = request("GET", "/api/state")
                    self.assertEqual(status, 200)
                    self.assertTrue(snapshot["apps"][0]["running"])
                    self.assertNotIn("private", json.dumps(snapshot))
                    self.assertEqual(request("GET", "/api/logs")[0], 200)
                    action({"action": "app.stop", "id": app.id})
                    self.assertFalse(panel.runner.running(app))
                    action({"action": "app.remove", "id": app.id})
                    action({"action": "profile.remove", "id": profile.id})
                    self.assertEqual(panel.store.apps(), [])
                    self.assertEqual(panel.store.profiles(), [])
                    action({"action": "diagnostics.run", "repair": False})
                    status, snapshot, _ = request("GET", "/api/state")
                    self.assertEqual(status, 200)
                    self.assertIsInstance(snapshot["diagnostics"]["checks"], list)
                    self.assertTrue(any(row["category"] == "dns" for row in snapshot["diagnostics"]["checks"]))
                finally:
                    if panel.worker:
                        panel.worker.join(timeout=40)
                    for app in panel.store.apps():
                        panel.runner.remove(app.id)
                    server.shutdown()
                    thread.join(timeout=5)
        self.assertEqual(before, json.loads(run(["ip", "-j", "-4", "route", "show", "table", "main"]).stdout))
