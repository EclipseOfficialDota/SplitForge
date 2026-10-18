import hashlib
import http.server
import io
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from splitforge.core import dependencies


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.cache = Path(self.temp.name) / 'cache'
        self.patcher = patch.object(dependencies, 'CACHE_ROOT', self.cache)
        self.patcher.start()
        self.environment = patch.dict(os.environ, {'SPLITFORGE_DOWNLOAD_CACHE': ''})
        self.environment.start()
        self.body = b'verified artifact\n' * 50000
        self.digest = hashlib.sha256(self.body).hexdigest()
        self.hits = {}
        outer = self
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                outer.hits[self.path] = outer.hits.get(self.path, 0) + 1
                status = 503 if self.path == '/retry' and outer.hits[self.path] == 1 else 404 if self.path == '/missing' else 200
                body = outer.body if status == 200 else b''
                self.send_response(status)
                if self.path != '/unknown-size':
                    self.send_header('Content-Length', str(len(body) + (100 if self.path == '/truncated' else 0)))
                self.end_headers()
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass
        self.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.environment.stop()
        self.patcher.stop()
        self.temp.cleanup()

    def test_retry_progress_verified_cache_and_offline_reuse(self):
        events = []
        with patch.object(dependencies.time, 'sleep'):
            result = dependencies.download(self.base + '/retry', self.digest, 2_000_000, progress=events.append)
        self.assertEqual(result, self.body)
        self.assertEqual(self.hits['/retry'], 2)
        self.assertTrue(any(event['phase'] == 'retry' for event in events))
        self.assertEqual(events[-1]['phase'], 'verified')
        self.assertEqual(events[-1]['percent'], 100)
        self.assertTrue(any(event['phase'] == 'downloading' and 0 < event['percent'] < 100 for event in events))
        cached = self.cache / (self.digest + '-retry')
        self.assertEqual(cached.read_bytes(), self.body)
        self.assertEqual(cached.stat().st_mode & 0o777, 0o600)
        with patch.object(dependencies.urllib.request, 'urlopen', side_effect=AssertionError('Must use cache')):
            self.assertEqual(dependencies.download(self.base + '/retry', self.digest, 2_000_000), self.body)

    def test_failed_primary_uses_alternative_without_weakening_digest(self):
        with patch.object(dependencies, '_alternatives', return_value=iter([self.base + '/valid'])):
            result = dependencies.download(self.base + '/missing', self.digest, 2_000_000)
        self.assertEqual(result, self.body)
        self.assertEqual(self.hits['/missing'], 1)
        self.assertEqual(self.hits['/valid'], 1)

    def test_corruption_and_size_limit_never_populate_cache_or_retry_bad_content(self):
        with self.assertRaisesRegex(RuntimeError, 'checksum'):
            dependencies.download(self.base + '/corrupt', '0' * 64, 2_000_000)
        self.assertEqual(self.hits['/corrupt'], 1)
        with self.assertRaisesRegex(RuntimeError, 'size limit'):
            dependencies.download(self.base + '/large', self.digest, 100)
        self.assertFalse(self.cache.exists())

    def test_truncated_response_is_retried_and_never_cached(self):
        with patch.object(dependencies.time, 'sleep'), patch.object(dependencies, '_alternatives', return_value=iter([])):
            with self.assertRaisesRegex(RuntimeError, 'official sources exhausted'):
                dependencies.download(self.base + '/truncated', self.digest, 2_000_000)
        self.assertEqual(self.hits['/truncated'], 3)
        self.assertFalse(self.cache.exists())

    def test_unknown_total_reports_bytes_then_verified_completion(self):
        events = []
        dependencies.download(self.base + '/unknown-size', self.digest, 2_000_000, progress=events.append)
        self.assertTrue(any(event['phase'] == 'downloading' and event['percent'] is None for event in events))
        self.assertEqual(events[-1]['percent'], 100)

    def test_official_go_alternatives_preserve_filename(self):
        url = 'https://go.dev/dl/go1.26.1.linux-amd64.tar.gz'
        self.assertEqual(list(dependencies._alternatives(url)), [
            'https://dl.google.com/go/go1.26.1.linux-amd64.tar.gz',
            'https://golang.google.cn/dl/go1.26.1.linux-amd64.tar.gz'])

    def test_github_alternative_resolves_only_the_named_release_asset(self):
        payload = {'assets': [{'name': 'other.zip', 'id': 4}, {'name': 'tool.zip', 'id': 123}]}
        with patch.object(dependencies.urllib.request, 'urlopen', return_value=io.BytesIO(json.dumps(payload).encode())):
            urls = list(dependencies._alternatives('https://github.com/org/repo/releases/download/v1/tool.zip'))
        self.assertEqual(urls, ['https://api.github.com/repos/org/repo/releases/assets/123'])

    def test_cache_write_failure_does_not_discard_a_verified_download(self):
        self.cache.write_text('a non-directory blocks cache creation')
        events = []
        data = dependencies.download(self.base + '/valid', self.digest, 2_000_000, progress=events.append)
        self.assertEqual(data, self.body)
        self.assertTrue(any('cache unavailable' in event['phase'] for event in events))
