import http.client
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from splitforge.state import Profile
from splitforge.web.server import Panel, PanelServer, read_token, serve


class WebTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.base = Path(directory.name)
        self.panel = Panel(self.base / "state.json", demo=True)
        self.token = "a-test-token-with-at-least-thirty-two-characters"
        self.server = PanelServer(("127.0.0.1", 0), self.panel, self.token)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)
        self.cookie = ""
        self.csrf = ""

    def close_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        if self.panel.worker:
            self.panel.worker.join(timeout=5)

    def request(self, method, path, data=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=10)
        supplied = {"Cookie": self.cookie, "X-SplitForge-CSRF": self.csrf}
        body = None
        if data is not None:
            body = json.dumps(data)
            supplied["Content-Type"] = "application/json"
        supplied.update(headers or {})
        connection.request(method, path, body=body, headers=supplied)
        response = connection.getresponse()
        raw = response.read()
        result = json.loads(raw) if "application/json" in response.getheader("Content-Type", "") else raw.decode()
        returned = dict(response.getheaders())
        connection.close()
        return response.status, result, returned

    def login(self):
        code, data, headers = self.request("POST", "/api/login", {"token": self.token})
        self.assertEqual(code, 200, data)
        self.cookie = headers["Set-Cookie"].split(";", 1)[0]
        self.csrf = data["csrf"]
        return headers

    def make_live(self):
        self.panel.demo = False
        self.panel._host_routes = Mock(return_value="[]")
        self.panel.route_baseline = "[]"

    def test_assets_are_packaged_and_state_requires_login(self):
        for path in ("/", "/app.js", "/app.css"):
            code, content, headers = self.request("GET", path)
            self.assertEqual(code, 200)
            self.assertGreater(len(content), 100)
            self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
            self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertEqual(self.request("GET", "/api/state")[0], 401)
        self.assertNotIn("Access-Control-Allow-Origin", headers)

    def test_token_session_csrf_and_logout(self):
        self.make_live()
        self.assertEqual(self.request("POST", "/api/login", {"token": "wrong"})[0], 401)
        headers = self.login()
        self.assertIn("HttpOnly", headers["Set-Cookie"])
        self.assertIn("SameSite=Strict", headers["Set-Cookie"])
        self.assertEqual(self.request("GET", "/api/state")[0], 200)
        with patch.object(self.panel, "submit") as submit:
            self.assertEqual(self.request("POST", "/api/action", {"action": "app.add"}, {"X-SplitForge-CSRF": "wrong"})[0], 403)
            submit.assert_not_called()
        self.assertEqual(self.request("POST", "/api/logout", {})[0], 200)
        self.assertEqual(self.request("GET", "/api/state")[0], 401)

    def test_host_and_origin_are_checked_and_demo_cannot_mutate(self):
        self.login()
        self.assertEqual(self.request("GET", "/api/state", headers={"Host": "attacker.example"})[0], 403)
        self.assertEqual(self.request("POST", "/api/action", {"action": "app.add"}, {"Origin": "https://attacker.example"})[0], 403)
        self.assertEqual(self.request("POST", "/api/action", {"action": "app.add"})[0], 403)
        self.assertFalse(self.panel.store.path.exists())

    def test_request_validation_and_expired_sessions(self):
        self.login()
        self.assertEqual(self.request("POST", "/api/action", [], {})[0], 400)
        self.assertEqual(self.request("POST", "/api/action", {}, {"Content-Type": "text/plain"})[0], 400)
        self.assertEqual(self.request("POST", "/api/action", {"padding": "x" * 65536})[0], 413)
        sid = self.cookie.split("=", 1)[1]
        with self.server.auth_lock:
            self.server.sessions[sid]["expires"] = 0
        self.assertEqual(self.request("GET", "/api/state")[0], 401)

    def test_login_is_rate_limited(self):
        self.make_live()
        for _ in range(10):
            self.assertEqual(self.request("POST", "/api/login", {"token": "wrong"})[0], 401)
        self.assertEqual(self.request("POST", "/api/login", {"token": self.token})[0], 429)

    def test_operations_are_async_serialized_and_failures_are_reported(self):
        self.make_live()
        self.login()
        release = threading.Event()
        def action(data, report):
            report("started")
            release.wait(timeout=3)
            raise ValueError("visible failure")
        with patch.object(self.panel, "_dispatch", side_effect=action):
            self.assertEqual(self.request("POST", "/api/action", {"action": "app.add"})[0], 202)
            self.assertEqual(self.request("POST", "/api/action", {"action": "app.add"})[0], 409)
            release.set()
            self.panel.worker.join(timeout=5)
        code, state, _ = self.request("GET", "/api/state")
        self.assertEqual(code, 200)
        self.assertFalse(state["busy"])
        self.assertEqual(state["jobs"][0]["state"], "failed")
        self.assertEqual(state["jobs"][0]["error"], "visible failure")

    def test_dispatch_uses_existing_routing_and_dependency_guards(self):
        self.make_live()
        self.panel.runner = Mock()
        self.panel._dispatch({"action": "app.bind", "id": "aa000001", "profile_id": "de000001"}, Mock())
        self.panel.runner.bind.assert_called_once_with("aa000001", "de000001", backup_profile_name=None)
        self.panel.runner.bind.reset_mock()
        self.panel._dispatch({"action": "app.bind", "id": "aa000001", "profile_id": "de000001", "backup_profile_id": "ab000002"}, Mock())
        self.panel.runner.bind.assert_called_once_with("aa000001", "de000001", backup_profile_name="ab000002")
        self.panel.manager = Mock()
        self.panel._dispatch({"action": "profile.import", "source": "socks5://127.0.0.1:1080", "name": "test"}, Mock())
        self.panel.manager.import_profile.assert_called_once_with("socks5://127.0.0.1:1080", name="test", replace_id=None)
        with patch("splitforge.web.server.dependencies.component_installed", return_value=False), \
             patch("splitforge.web.server.dependencies.install", return_value="installed") as install:
            self.panel._dispatch({"action": "cores.install", "names": ["slipstream-client"]}, Mock())
        self.assertEqual([call.args[0] for call in install.call_args_list], ["base", "xray", "tun2socks", "slipstream-client"])

    @unittest.skipUnless(os.name == "posix", "State locking uses POSIX")
    def test_snapshot_never_exposes_profile_credentials(self):
        self.make_live()
        self.panel.store.save_profile(Profile("test", "socks5", {"password": "never-send-this-secret"}))
        self.panel.manager.status = Mock(return_value={"active": False, "namespace": False, "bandwidth": {"rx": 0, "tx": 0}})
        self.login()
        code, state, _ = self.request("GET", "/api/state")
        self.assertEqual(code, 200)
        self.assertNotIn("never-send-this-secret", json.dumps(state))
        self.assertNotIn("config", state["profiles"][0])

    def test_network_binding_rejects_public_interfaces(self):
        with self.assertRaises(ValueError):
            serve(Path("/tmp/unused.json"), host="0.0.0.0", demo=True)

    @unittest.skipUnless(os.name == "posix", "POSIX token permissions")
    def test_token_is_private_and_rejects_public_read_permissions(self):
        path = self.base / "web.token"
        token = read_token(path)
        self.assertGreaterEqual(len(token), 32)
        self.assertEqual(read_token(path), token)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        path.chmod(0o644)
        with self.assertRaises(ValueError):
            read_token(path)
