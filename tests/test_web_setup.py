import contextlib
import dataclasses
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from splitforge.cli import app
from splitforge.web import setup


class WebSetupTests(unittest.TestCase):
    def test_validation_rejects_config_injection_private_ips_and_port_collision(self):
        for address in ('example.com; include /etc/passwd', 'a\nb.com', 'https://example.com',
                        'example.com/path', '*.example.com', '127.0.0.1', '10.1.2.3', '-bad.example'):
            with self.subTest(address=address), self.assertRaises(ValueError):
                setup.WebSettings(address=address).validate()
        with self.assertRaises(ValueError):
            setup.WebSettings(address='example.com', port=8765).validate()
        with self.assertRaises(ValueError):
            setup.WebSettings(address='example.com', port=80).validate()
        with self.assertRaises(ValueError):
            setup.WebSettings(mode='local', port=True).validate()
        self.assertEqual(setup.validate_address('Panel.Example.com.'), 'panel.example.com')

    def test_ip_and_domain_certificates_use_correct_acme_flags_and_separate_lineages(self):
        domain = setup.WebSettings(address='panel.example.com').validate()
        ip = setup.WebSettings(address='8.8.8.8').validate()
        self.assertIn('--domain', setup.certificate_command(domain))
        command = setup.certificate_command(ip)
        self.assertIn('--ip-address', command)
        self.assertIn('--required-profile', command)
        self.assertIn('shortlived', command)
        self.assertIn('--webroot', command)
        self.assertNotEqual(domain.cert_name, ip.cert_name)
        self.assertIn('--foreground', setup.service_text(domain))

    def test_proxy_checks_public_host_and_origin_and_default_ports(self):
        settings = setup.WebSettings(address='example.com', port=443).validate()
        text = setup.nginx_text(settings)
        for part in ('"example.com" 1;', '"example.com:443" 1;', '"https://example.com" 1;',
                     '"https://example.com:443" 1;', 'return 403', 'return 421',
                     'secure httponly samesite=strict', '127.0.0.1:8765', '/.well-known/acme-challenge/'):
            self.assertIn(part, text)
        self.assertNotIn('ssl_certificate ', setup.nginx_text(settings, challenge_only=True))
        settings.mode = 'http'
        settings.port = 9090
        self.assertNotIn('ssl_certificate ', setup.nginx_text(settings))
        self.assertNotIn('secure httponly', setup.nginx_text(settings))

    def test_cli_setup_and_first_launch_preserve_state_and_skip_foreground(self):
        with patch('splitforge.web.setup.deploy') as deploy, patch('splitforge.web.server.serve') as serve:
            result = CliRunner().invoke(app, ['--state', '/root/custom.json', 'web', 'setup',
                                             '--address', 'example.com', '--port', '9443', '--agree-tos'])
        self.assertEqual(result.exit_code, 0, f'{result.output}: {result.exception}')
        self.assertEqual(deploy.call_args.args[0].state, '/root/custom.json')
        self.assertEqual(deploy.call_args.args[0].port, 9443)
        self.assertTrue(deploy.call_args.kwargs['agree_tos'])
        serve.assert_not_called()
        with patch('splitforge.cli.sys') as cli_sys, patch('splitforge.web.setup.load_settings', return_value=None), \
                patch('splitforge.web.setup.wizard') as wizard, patch('splitforge.web.server.serve'):
            cli_sys.stdin.isatty.return_value = True
            result = CliRunner().invoke(app, ['web'])
        self.assertEqual(result.exit_code, 0, f'{result.output}: {result.exception}')
        wizard.assert_called_once()

    @contextlib.contextmanager
    def deployment(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.ExitStack() as stack:
            base = Path(directory)
            for name in ('CONFIG', 'UNIT', 'NGINX', 'LEGACY_NGINX', 'CHALLENGE', 'RENEW_SERVICE', 'RENEW_TIMER'):
                stack.enter_context(patch.object(setup, name, base / name.lower()))
            stack.enter_context(patch.object(setup, 'require_root'))
            stack.enter_context(patch.object(setup, '_check_internal_port'))
            stack.enter_context(patch.object(setup, '_backend_healthy'))
            stack.enter_context(patch.object(setup, '_public_healthy'))
            stack.enter_context(patch.object(setup, 'ensure_tools'))
            stack.enter_context(patch('splitforge.web.server.read_token', return_value='private-token'))
            stack.enter_context(patch.object(setup.shutil, 'which', return_value=None))
            def command(argv, **kwargs):
                code = 1 if argv[1:2] in (['is-active'], ['is-enabled']) else 0
                return subprocess.CompletedProcess(argv, code, stdout='', stderr='')
            calls = stack.enter_context(patch.object(setup, 'run', side_effect=command))
            yield base, calls

    def test_local_setup_persists_private_settings_and_permanent_service(self):
        with self.deployment() as (base, calls):
            settings = setup.WebSettings(mode='local', port=9091)
            setup.deploy(settings, report=lambda message: None)
            self.assertEqual(json.loads(setup.CONFIG.read_text()), dataclasses.asdict(settings))
            self.assertEqual(setup.CONFIG.stat().st_mode & 0o777, 0o600)
            self.assertIn('WantedBy=multi-user.target', setup.UNIT.read_text())
            self.assertFalse(setup.NGINX.exists())
            self.assertTrue(any(call.args[0] == ['systemctl', 'restart', setup.UNIT.name] for call in calls.call_args_list))

    def test_certificate_failure_rolls_back_previous_owned_files(self):
        with self.deployment() as (base, calls):
            previous = setup.MARKER + 'previous deployment\n'
            setup.NGINX.write_text(previous)
            setup.UNIT.write_text(previous)
            setup.CONFIG.write_text('{"old": true}\n')
            def command(argv, **kwargs):
                if str(argv[0]) == str(setup.CERTBOT):
                    return subprocess.CompletedProcess(argv, 1, stdout='', stderr='ACME challenge rejected')
                return subprocess.CompletedProcess(argv, 0, stdout='', stderr='')
            calls.side_effect = command
            with self.assertRaisesRegex(RuntimeError, 'ACME challenge rejected'):
                setup.deploy(setup.WebSettings(address='example.com'), agree_tos=True, report=lambda message: None)
            self.assertEqual(setup.NGINX.read_text(), previous)
            self.assertEqual(setup.UNIT.read_text(), previous)
            self.assertEqual(setup.CONFIG.read_text(), '{"old": true}\n')
            self.assertFalse(setup.RENEW_TIMER.exists())

    def test_public_readiness_failure_is_not_reported_as_success(self):
        with self.deployment(), patch.object(setup, '_public_healthy', side_effect=RuntimeError('Not reachable')):
            with self.assertRaisesRegex(RuntimeError, 'Not reachable'):
                setup.deploy(setup.WebSettings(address='example.com', mode='http'), report=lambda message: None)
            self.assertFalse(setup.CONFIG.exists())
            self.assertFalse(setup.UNIT.exists())

    def test_https_installs_renewal_timer_but_requires_explicit_terms(self):
        with self.deployment():
            settings = setup.WebSettings(address='example.com')
            with self.assertRaisesRegex(ValueError, 'agree-tos'):
                setup.deploy(settings)
            setup.deploy(settings, agree_tos=True, report=lambda message: None)
            self.assertIn('00,12:00:00', setup.RENEW_TIMER.read_text())
            self.assertIn(settings.cert_name, setup.RENEW_SERVICE.read_text())
            self.assertIn('systemctl reload nginx', setup.RENEW_SERVICE.read_text())
