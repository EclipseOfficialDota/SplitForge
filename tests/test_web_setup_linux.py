"""Opt-in real systemd startup and generated nginx HTTPS proxy checks."""
import contextlib
import http.cookiejar
import json
import os
import shutil
import socket
import ssl
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from unittest.mock import patch

from splitforge.core.netns import run
from splitforge.web import setup
from splitforge.web.server import Panel, PanelServer


def available_port():
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        return listener.getsockname()[1]


@unittest.skipUnless(os.environ.get('SPLITFORGE_INTEGRATION') == '1' and os.geteuid() == 0,
                     'Enable root/systemd integration explicitly')
class WebSetupLinuxTests(unittest.TestCase):
    def test_actual_permanent_service_restarts_and_preserves_host_routes(self):
        before = run(['ip', '-4', 'route', 'show', 'table', 'main']).stdout
        unit = Path('/etc/systemd/system', f'splitforge-test-web-{uuid.uuid4().hex[:8]}.service')
        with tempfile.TemporaryDirectory() as directory, contextlib.ExitStack() as stack:
            base = Path(directory)
            for name in ('CONFIG', 'NGINX', 'LEGACY_NGINX', 'CHALLENGE', 'RENEW_SERVICE', 'RENEW_TIMER'):
                stack.enter_context(patch.object(setup, name, base / name.lower()))
            stack.enter_context(patch.object(setup, 'UNIT', unit))
            settings = setup.WebSettings(mode='local', port=available_port(), state=str(base / 'state.json'),
                                         token_file=str(base / 'token'))
            try:
                setup.deploy(settings, report=lambda message: None)
                self.assertEqual(run(['systemctl', 'is-active', unit.name]).stdout.strip(), 'active')
                self.assertEqual(run(['systemctl', 'is-enabled', unit.name]).stdout.strip(), 'enabled')
                run(['systemctl', 'restart', unit.name])
                setup._backend_healthy(settings)
                self.assertEqual(run(['ip', '-4', 'route', 'show', 'table', 'main']).stdout, before)
            finally:
                run(['systemctl', 'disable', '--now', unit.name], check=False)
                unit.unlink(missing_ok=True)
                run(['systemctl', 'daemon-reload'])

    @unittest.skipUnless(shutil.which('nginx'), 'nginx is required for the real proxy check')
    def test_generated_https_proxy_login_secure_cookie_origin_and_host_guards(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            base.chmod(0o755)
            cert, key = base / 'cert.pem', base / 'key.pem'
            run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                 '-keyout', str(key), '-out', str(cert), '-subj', '/CN=localhost',
                 '-addext', 'subjectAltName=DNS:localhost'])
            token = 'test-token-' + uuid.uuid4().hex
            with PanelServer(('127.0.0.1', 0), Panel(base / 'state.json'), token) as backend:
                thread = threading.Thread(target=backend.serve_forever, daemon=True)
                thread.start()
                settings = setup.WebSettings(address='panel.example.test', port=available_port(), backend_port=backend.server_port)
                text = setup.nginx_text(settings)
                # Use only the HTTPS virtual host, with an explicitly trusted local fixture certificate.
                text = text[text.index('map $http_host'):]
                text = text.replace(f'/etc/letsencrypt/live/{settings.cert_name}/fullchain.pem', str(cert))
                text = text.replace(f'/etc/letsencrypt/live/{settings.cert_name}/privkey.pem', str(key))
                config = base / 'nginx.conf'
                config.write_text(f'pid {base}/nginx.pid;\nerror_log {base}/error.log;\nevents {{}}\nhttp {{\n{text}\n}}\n')
                run(['nginx', '-t', '-p', str(base), '-c', str(config)])
                process = subprocess.Popen(['nginx', '-p', str(base), '-c', str(config), '-g', 'daemon off;'],
                                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                try:
                    context = ssl.create_default_context(cafile=str(cert))
                    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                        urllib.request.HTTPSHandler(context=context), urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
                    url = f'https://localhost:{settings.port}'
                    def request(path, data=None, **headers):
                        return urllib.request.Request(url + path, data=None if data is None else json.dumps(data).encode(),
                            headers={'Host': f'{settings.address}:{settings.port}', 'Content-Type': 'application/json', **headers})
                    for attempt in range(30):
                        try:
                            opener.open(request('/api/session'), timeout=2).close()
                            break
                        except OSError:
                            if process.poll() is not None:
                                self.fail((base / 'error.log').read_text())
                            time.sleep(0.1)
                    with opener.open(request('/api/login', {'token': token}, Origin=settings.url), timeout=5) as response:
                        self.assertIn('secure', response.headers['Set-Cookie'].lower())
                        csrf = json.load(response)['csrf']
                    with opener.open(request('/api/state'), timeout=10) as response:
                        self.assertEqual(json.load(response)['profiles'], [])
                    for headers, expected in (({'Origin': 'https://evil.example'}, 403), ({'Host': 'evil.example'}, 421)):
                        with self.assertRaises(urllib.error.HTTPError) as caught:
                            opener.open(request('/api/session', **headers), timeout=5)
                        self.assertEqual(caught.exception.code, expected)
                    with opener.open(request('/api/logout', {}, Origin=settings.url, **{'X-SplitForge-CSRF': csrf}), timeout=5) as response:
                        self.assertEqual(response.status, 200)
                finally:
                    process.terminate()
                    process.communicate(timeout=10)
                    backend.shutdown()
                    thread.join(timeout=5)
