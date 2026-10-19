"""Loopback-only HTTP control plane with authenticated sessions and CSRF checks."""
from __future__ import annotations

import dataclasses
import hashlib
import hmac
import ipaddress
import json
import os
import platform
import secrets
import shlex
import shutil
import stat
import threading
import time
from collections import deque
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import psutil

from splitforge import __version__
from splitforge.core import dependencies
from splitforge.core.netns import atomic_secret, require_root, run
from splitforge.core.runner import Runner
from splitforge.protocols.manager import ProtocolManager
from splitforge.state import AppBinding, Profile, StateStore

STATIC = Path(__file__).parent / "static"
SESSION_SECONDS = 8 * 3600


def read_token(path: Path) -> str:
    path = path.expanduser().absolute()
    if not path.exists() and not path.is_symlink():
        atomic_secret(path, secrets.token_urlsafe(32) + "\n")
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
        raise ValueError("Token file must be a regular file owned by the current user with mode 0600")
    token = path.read_text(encoding="utf-8").strip()
    if len(token) < 32 or len(token) > 256 or not token.isascii() or any(c.isspace() for c in token):
        raise ValueError("Token must contain 32–256 ASCII characters without whitespace")
    return token


class Panel:
    def __init__(self, state: Path, *, demo=False):
        self.store = StateStore(state)
        self.manager = ProtocolManager(self.store)
        self.runner = Runner(self.store, self.manager)
        self.demo = demo
        self.lock = threading.Lock()
        self.jobs = deque(maxlen=30)
        self.busy = False
        self.cache = None
        self.cache_time = 0.0
        self.cache_lock = threading.Lock()
        self.route_baseline = None if demo else self._host_routes()
        self.worker = None
        self.diagnostics = None
        self.app_tests = {}
        self.exports = {}
        from splitforge.core.traffic import TrafficStore
        self.traffic = TrafficStore(self.store)

    @staticmethod
    def _host_routes():
        return run(["ip", "-j", "-4", "route", "show", "table", "main"], timeout=5).stdout

    def snapshot(self):
        with self.cache_lock:
            if self.cache is None or time.monotonic() - self.cache_time > 3:
                self.cache = self._snapshot()
                self.cache_time = time.monotonic()
            result = dict(self.cache)
        with self.lock:
            result["jobs"] = [dict(job, messages=list(job["messages"])) for job in self.jobs]
            result["busy"] = self.busy
            result["diagnostics"] = self.diagnostics
            result['app_tests'] = dict(self.app_tests)
        return result

    def _snapshot(self):
        if self.demo:
            profiles = [Profile("reality-frankfurt", "vless", {}, id="de000001", slot=1,
                               exit_ip="192.0.2.42", country="DE", latency_ms=42),
                        Profile("wireguard-us", "wireguard", {}, id="ab000002", slot=2,
                               exit_ip="198.51.100.18", country="US", latency_ms=108),
                        Profile("dns-backup", "dnstt", {}, id="cd000003", slot=3)]
            apps = [AppBinding("telegram_bot.py", ["/usr/bin/python3", "/srv/bots/telegram_bot.py"],
                               id="aa000001", user="root", profile_id=profiles[0].id, enabled=True),
                    AppBinding("price_scraper.py", ["/usr/bin/python3", "/srv/scraper.py"],
                               id="aa000002", user="worker", profile_id=profiles[1].id, enabled=True),
                    AppBinding("nightly_backup.sh", ["/bin/bash", "/srv/backup.sh"], id="aa000003", user="root"),
                    AppBinding("web-worker.service", service="web-worker.service", id="aa000004", user="www-data")]
        else:
            profiles, apps = self.store.profiles(), self.store.apps()
        profile_rows = []
        for index, profile in enumerate(profiles):
            live = ({"active": index < 2, "namespace": index < 2, "bandwidth": {"rx": (index + 1) * 18423428, "tx": 2457000}}
                    if self.demo else self.manager.status(profile.id))
            profile_rows.append({"id": profile.id, "name": profile.name, "protocol": profile.protocol,
                "exit_ip": profile.exit_ip, "country": profile.country, "latency_ms": profile.latency_ms,
                "doh_url": profile.doh_url, "doh_ip": profile.doh_ip, **live})
        components = [{"id": name, "description": description, "installed": dependencies.component_installed(name)}
                      for name, (_, description) in dependencies.COMPONENTS.items()]
        try:
            traffic = self.traffic.snapshot() if not self.demo else self._demo_traffic(profiles, apps)
            if not self.demo:
                from splitforge.core.traffic import unit_name
                traffic['collector_active'] = run(['systemctl', 'is-active', '--quiet', unit_name(self.store)], check=False, timeout=5).returncode == 0
        except Exception as error:
            traffic = {'apps': {}, 'profiles': {}, 'events': [], 'error': str(error)[:300]}
        return {"version": __version__, "demo": self.demo, "host": "forge-vps" if self.demo else platform.node(),
            "route_unchanged": self.demo or self._host_routes() == self.route_baseline,
            "memory_percent": round(psutil.virtual_memory().percent, 1), "cpu_percent": psutil.cpu_percent(),
            "uptime": int(time.time() - psutil.boot_time()), "profiles": profile_rows,
            "apps": [{"id": a.id, "name": a.name, "user": a.user, "cwd": a.cwd, "service": a.service,
                      "command": shlex.join(a.argv), "profile_id": a.profile_id, "enabled": a.enabled,
                      "running": a.enabled if self.demo else self.runner.running(a),
                      "primary_profile_id": a.primary_profile_id, "backup_profile_id": a.backup_profile_id,
                      "failover_enabled": a.failover_enabled} for a in apps],
            "components": components, 'traffic': traffic}

    @staticmethod
    def _demo_traffic(profiles, apps):
        from splitforge.core.traffic import empty_data, new_row, update_row
        data = empty_data()
        now = time.time()
        for kind, entities in [('profiles', profiles), ('apps', apps)]:
            for index, entity in enumerate(entities):
                row = new_row()
                for point in range(60):
                    update_row(row, ('demo', point * (index + 1) * 18000, point * 4000), now - (60 - point) * 5)
                row['quota'] = 64 * 1024 * 1024
                data[kind][entity.id] = row
        data['updated'] = now
        data['collector_active'] = True
        return data

    def submit(self, data):
        if self.demo:
            raise PermissionError("Read-only demo: no server configuration was changed")
        if not isinstance(data, dict) or not isinstance(data.get("action"), str) or data.get("action") not in {
                "profile.import", "profile.dns-tunnel", "profile.start", "profile.stop", "profile.test", "profile.remove",
                "profile.dns", "app.add", "app.bind", "app.start", "app.stop", "app.remove", "app.test", "cores.install", "diagnostics.run", "backup.export", "backup.restore", "traffic.enable", "traffic.quota"}:
            raise ValueError("Unknown action")
        with self.lock:
            if self.busy:
                raise BlockingIOError("An operation is still running; wait for it to finish")
            self.busy = True
            job = {"id": secrets.token_hex(8), "action": data["action"], "state": "running",
                   "created": time.time(), "messages": [], "error": ""}
            self.jobs.appendleft(job)
        self.worker = threading.Thread(target=self._work, args=(job, dict(data)), daemon=False)
        self.worker.start()
        return job["id"]

    def _work(self, job, data):
        try:
            result = self._dispatch(data, lambda message: self._message(job, message))
            with self.lock:
                job["state"] = "success"
                if result is not None:
                    job['result'] = result
        except Exception as error:
            with self.lock:
                job["state"], job["error"] = "failed", str(error)[:1000]
        finally:
            with self.lock:
                self.busy = False
            with self.cache_lock:
                self.cache_time = 0

    def _message(self, job, message):
        with self.lock:
            if isinstance(message, dict):
                job['progress'] = dict(message)
                message = dependencies.progress_text(message)
            job["messages"].append(str(message)[:1000])
            del job["messages"][:-30]

    @staticmethod
    def _text(data, key, default="", limit=16384):
        value = data.get(key, default)
        if not isinstance(value, str) or len(value) > limit or "\0" in value:
            raise ValueError(f"Invalid {key}")
        return value.strip()

    def _dispatch(self, data, report):
        action = data["action"]
        target = self._text(data, "id", limit=80)
        if action == 'traffic.enable':
            from splitforge.core.traffic import ensure_service
            ensure_service(self.store)
            return
        if action == 'traffic.quota':
            kind = self._text(data, 'kind', limit=20)
            if kind not in ('apps', 'profiles'):
                raise ValueError('Choose apps or profiles')
            if 'limit' not in data:
                raise ValueError('Specify a traffic limit or an explicit disabled value')
            self.traffic.set_quota(kind, target, data.get('limit'), warning=data.get('warning', 80), reset=data.get('reset', False))
            report('Traffic budget saved; exhausted targets stay stopped until explicitly started')
            return
        if action in {'backup.export', 'backup.restore'}:
            from splitforge.core.backup import LIMIT, capture, decrypt, encrypt, restore_backup
            password = data.get('password')
            if not isinstance(password, str) or not 12 <= len(password.encode()) <= 1024:
                raise ValueError('Backup password must contain 12–1024 UTF-8 bytes')
            if action == 'backup.export':
                report('Encrypting configuration backup…')
                archive = encrypt(capture(self.store), password)
                identifier = secrets.token_hex(16)
                with self.lock:
                    self.exports[identifier] = archive
                    while len(self.exports) > 6:
                        self.exports.pop(next(iter(self.exports)))
                return {'download': identifier}
            if data.get('confirm') is not True:
                raise ValueError('Confirm replacement of current registrations before restoring')
            document = decrypt(self._text(data, 'archive', limit=LIMIT * 2), password)
            restore_backup(self.store, self.manager, self.runner, document, password, start=False, report=report)
            with self.lock:
                self.app_tests.clear()
            return
        if action == "diagnostics.run":
            repair = data.get('repair', False)
            if not isinstance(repair, bool):
                raise ValueError('repair must be a boolean')
            from splitforge.core.diagnostics import diagnose
            result = diagnose(self.store, self.manager, self.runner, repair=repair, report=report,
                              route_baseline=self.route_baseline)
            with self.lock:
                self.diagnostics = result
            report(f'Checks completed: {result["errors"]} errors, {result["warnings"]} warnings')
        elif action == 'app.test':
            result = self.runner.test(target)
            with self.lock:
                self.app_tests[target] = result
            report(json.dumps(result))
        elif action == "profile.import":
            profile = self.manager.import_profile(self._text(data, "source"),
                name=self._text(data, "name", limit=80) or None, replace_id=target or None)
            report(f"Saved profile {profile.name}")
        elif action == "profile.dns-tunnel":
            profile = self.manager.dns_tunnel(self._text(data, "name", limit=80), self._text(data, "protocol"),
                self._text(data, "domain"), self._text(data, "resolver"), public_key=self._text(data, "public_key"),
                certificate=self._text(data, "certificate"), replace_id=target or None)
            report(f"Saved profile {profile.name}")
        elif action in {"profile.start", "profile.stop", "profile.test"}:
            result = getattr(self.manager, action.split(".")[1])(target)
            if result:
                report(json.dumps(result))
        elif action == "profile.remove":
            self.manager.remove(target)
        elif action == "profile.dns":
            profile = self.store.profile(target)
            if self.manager.netns.exists(profile):
                raise ValueError("Stop the profile before changing DNS")
            self.store.save_profile(dataclasses.replace(profile, doh_url=self._text(data, "url"), doh_ip=self._text(data, "bootstrap")))
        elif action == "app.add":
            name = self._text(data, "name", limit=80)
            if any(a.name == name for a in self.store.apps()):
                raise ValueError("Application name already exists")
            service = self._text(data, "service", limit=200) or None
            argv = [] if service else shlex.split(self._text(data, "command"))
            if argv:
                executable = shutil.which(argv[0])
                if not executable:
                    raise ValueError("Executable not found on the server")
                argv[0] = executable
            binding = AppBinding(name, argv, user=self._text(data, "user", "root", 80),
                                 cwd=self._text(data, "cwd", "/", 4096), service=service)
            self.runner._identity(binding.user)
            self.runner._validate_service(binding)
            self.store.save_app(binding)
            report("Application registered; assign a route to start it")
        elif action == "app.bind":
            profile = self._text(data, "profile_id", limit=80)
            backup = self._text(data, 'backup_profile_id', limit=80)
            updated = self.runner.bind(target, profile or None, backup_profile_name=backup or None)
            if backup:
                report('Automatic primary/backup policy saved; switches restart this application.')
                if not self.runner.running(updated):
                    report('Workload remains stopped; the monitor will retry the configured tunnels. Check Live logs.')
        elif action == 'app.start':
            binding = self.store.app(target)
            self.runner.bind(binding.id, binding.profile_id, preserve_failover=True)
        elif action in {"app.stop", "app.remove"}:
            getattr(self.runner, action.split(".")[1])(target)
        elif action == "cores.install":
            names = data.get("names")
            if not isinstance(names, list) or len(names) > len(dependencies.COMPONENTS) or not all(isinstance(n, str) for n in names):
                raise ValueError("Select valid components")
            if not names:
                raise ValueError("Select at least one component")
            failures = []
            for name in dependencies.component_plan(names):
                report(f"Checking {name}…")
                try:
                    report(f"{name}: already installed; skipped" if dependencies.component_installed(name) else dependencies.install(name, progress=report))
                except Exception as error:
                    failures.append(name)
                    report(f"Failed {name}: {error}")
            if failures:
                raise RuntimeError("Failed: " + ", ".join(failures) + "; successful installations were retained")
        report("Operation completed")

    def logs(self):
        if self.demo:
            return "[demo] Control plane ready\n[demo] 2 profiles active · sample data\n[demo] No network configuration is changed\n"
        return run(["journalctl", "--no-pager", "-n", "100", "-o", "short-iso", "-u", "splitforge-*"], timeout=8).stdout[-100000:]

    def browse(self, path):
        if self.demo:
            return {"path": "/srv", "parent": "/", "entries": [{"name": "bots", "path": "/srv/bots", "directory": True},
                {"name": "telegram_bot.py", "path": "/srv/telegram_bot.py", "directory": False}]}
        directory = Path(path).expanduser()
        if not directory.is_absolute() or not directory.is_dir():
            raise ValueError("Choose an existing absolute directory")
        entries = []
        for item in sorted(directory.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))[:200]:
            entries.append({"name": item.name, "path": str(item), "directory": item.is_dir()})
        return {"path": str(directory), "parent": str(directory.parent), "entries": entries}


class PanelServer(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False

    def __init__(self, address, panel, token):
        self.panel, self.token = panel, token
        self.sessions = {}
        self.auth_lock = threading.Lock()
        self.failures = deque(maxlen=20)
        self.slots = threading.BoundedSemaphore(16)
        super().__init__(address, Handler)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()


class Handler(BaseHTTPRequestHandler):
    server_version = "SplitForge"
    sys_version = ""

    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def log_message(self, *_):
        pass  # Never log cookies, tokens, commands or imported credentials.

    def _send(self, status, data, mime="application/json", cookie=None):
        body = json.dumps(data, ensure_ascii=False).encode() if mime == "application/json" else data
        self.send_response(status)
        self.send_header("Content-Type", mime + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(body)

    def _origin(self):
        host = self.headers.get("Host", "")
        allowed = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
        if host not in allowed:
            raise PermissionError("Invalid request host")
        origin = self.headers.get("Origin")
        if origin is not None and origin != "http://" + host:
            raise PermissionError("Cross-origin requests are not allowed")

    def _session(self):
        self._origin()
        cookie = SimpleCookie()
        cookie.load(self.headers.get("Cookie", ""))
        session_id = cookie["sf_session"].value if "sf_session" in cookie else ""
        with self.server.auth_lock:
            now = time.monotonic()
            self.server.sessions = {key: value for key, value in self.server.sessions.items() if value["expires"] > now}
            session = self.server.sessions.get(session_id)
        return session_id, session

    def do_GET(self):
        try:
            self._origin()
            url = urlsplit(self.path)
            files = {"/": ("index.html", "text/html"), "/app.css": ("app.css", "text/css"),
                     "/app.js": ("app.js", "text/javascript"), "/i18n.js": ("i18n.js", "text/javascript")}
            if url.path in files:
                filename, mime = files[url.path]
                self._send(200, (STATIC / filename).read_bytes(), mime)
                return
            _, session = self._session()
            if url.path == "/api/session":
                self._send(200, {"authenticated": session is not None, "csrf": session["csrf"] if session else "",
                                 "demo": self.server.panel.demo, "version": __version__})
                return
            if not session:
                self._send(401, {"error": "Sign in to continue"})
                return
            if url.path == "/api/state":
                self._send(200, self.server.panel.snapshot())
            elif url.path == "/api/logs":
                self._send(200, {"text": self.server.panel.logs()})
            elif url.path == "/api/browse":
                self._send(200, self.server.panel.browse(parse_qs(url.query).get("path", ["/"])[0]))
            elif url.path == '/api/backup':
                identifier = parse_qs(url.query).get('id', [''])[0]
                with self.server.panel.lock:
                    archive = self.server.panel.exports.get(identifier)
                if archive is None:
                    self._send(404, {'error': 'Backup download expired; export a new backup'})
                else:
                    self._send(200, archive.encode('ascii'), 'application/octet-stream')
            else:
                self._send(404, {"error": "Not found"})
        except (ValueError, KeyError) as error:
            self._send(400, {"error": str(error)[:1000]})
        except PermissionError as error:
            self._send(403, {"error": str(error)})
        except Exception:
            self._send(500, {"error": "Could not read server state; inspect the local server terminal"})

    def do_POST(self):
        try:
            self._origin()
            if self.headers.get_content_type() != "application/json" or self.headers.get("Transfer-Encoding"):
                raise ValueError("Use an application/json request")
            length = int(self.headers.get("Content-Length", "0"))
            _, upload_session = self._session()
            upload = (urlsplit(self.path).path == '/api/action' and not self.server.panel.demo and upload_session is not None
                      and hmac.compare_digest(self.headers.get('X-SplitForge-CSRF', ''), upload_session['csrf']))
            if not 0 < length <= (16 * 1024 * 1024 if upload else 65536):
                self._send(413, {"error": "Request is empty or exceeds its allowed size"})
                return
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError("Expected a JSON object")
            path = urlsplit(self.path).path
            if path == "/api/login":
                supplied = data.get("token", "")
                if not isinstance(supplied, str) or len(supplied) > 256:
                    raise ValueError("Invalid token")
                with self.server.auth_lock:
                    now = time.monotonic()
                    if len([t for t in self.server.failures if now - t < 60]) >= 10:
                        self._send(429, {"error": "Too many sign-in attempts; wait one minute"})
                        return
                    valid = self.server.panel.demo or hmac.compare_digest(hashlib.sha256(supplied.encode()).digest(),
                                                                       hashlib.sha256(self.server.token.encode()).digest())
                    if not valid:
                        self.server.failures.append(now)
                        self._send(401, {"error": "Incorrect access token"})
                        return
                    self.server.sessions = {key: value for key, value in self.server.sessions.items() if value["expires"] > now}
                    if len(self.server.sessions) >= 32:
                        self._send(429, {"error": "Too many active sessions; sign out or wait for expiry"})
                        return
                    sid, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
                    self.server.sessions[sid] = {"csrf": csrf, "expires": now + SESSION_SECONDS}
                self._send(200, {"csrf": csrf}, cookie=f"sf_session={sid}; HttpOnly; SameSite=Strict; Path=/; Max-Age={SESSION_SECONDS}")
                return
            sid, session = self._session()
            if not session:
                self._send(401, {"error": "Sign in to continue"})
                return
            if not hmac.compare_digest(self.headers.get("X-SplitForge-CSRF", ""), session["csrf"]):
                raise PermissionError("Invalid CSRF token")
            if path == "/api/logout":
                with self.server.auth_lock:
                    self.server.sessions.pop(sid, None)
                self._send(200, {"ok": True}, cookie="sf_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0")
            elif path == "/api/action":
                self._send(202, {"job": self.server.panel.submit(data)})
            else:
                self._send(404, {"error": "Not found"})
        except (ValueError, KeyError) as error:
            self._send(400, {"error": str(error)[:1000]})
        except PermissionError as error:
            self._send(403, {"error": str(error)})
        except BlockingIOError as error:
            self._send(409, {"error": str(error)})
        except Exception:
            self._send(500, {"error": "Request failed; inspect the local server terminal"})


def serve(state: Path, *, host="127.0.0.1", port=8765, token_file=Path("/etc/splitforge/web.token"), demo=False):
    if host != "localhost" and (not ipaddress.ip_address(host).is_loopback or ":" in host):
        raise ValueError("Use an IPv4 loopback address and SSH port forwarding for remote access")
    if host not in {"127.0.0.1", "localhost"}:
        raise ValueError("Use 127.0.0.1 or localhost")
    if not 1 <= port <= 65535:
        raise ValueError("Port must be between 1 and 65535")
    if not demo:
        require_root()
    token = "" if demo else read_token(token_file)
    with PanelServer((host, port), Panel(state, demo=demo), token) as server:
        print(f"SplitForge web panel: http://127.0.0.1:{server.server_port}", flush=True)
        print("Read-only demo; click Explore demo to enter." if demo else f"Access token file: {token_file} (read with sudo cat)", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            if server.panel.worker and server.panel.worker.is_alive():
                print("Waiting for the current operation to finish before closing the panel…", flush=True)
                server.panel.worker.join()
