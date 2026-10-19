"""Transactional systemd/nginx deployment with automatic ACME certificates."""
from __future__ import annotations

import fcntl
import hashlib
import ipaddress
import json
import os
import re
import shutil
import socket
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from splitforge.core.netns import atomic_secret, require_root, run, unit_word

CONFIG = Path('/etc/splitforge/web.json')
UNIT = Path('/etc/systemd/system/splitforge-web.service')
NGINX = Path('/etc/nginx/conf.d/splitforge-web.conf')
LEGACY_NGINX = Path('/etc/nginx/conf.d/splitforge-panel.conf')
CHALLENGE = Path('/var/www/splitforge-acme')
CERTBOT = Path('/opt/splitforge-certbot/bin/certbot')
RENEW_SERVICE = Path('/etc/systemd/system/splitforge-web-renew.service')
RENEW_TIMER = Path('/etc/systemd/system/splitforge-web-renew.timer')
MARKER = '# Managed by SplitForge web setup\n'


@dataclass
class WebSettings:
    mode: str = 'https'
    address: str = ''
    port: int = 9090
    backend_port: int = 8765
    email: str = ''
    state: str = '/etc/splitforge/state.json'
    token_file: str = '/etc/splitforge/web.token'

    def validate(self):
        if self.mode not in {'local', 'http', 'https'}:
            raise ValueError('Choose local, http or https')
        for port in (self.port, self.backend_port):
            if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
                raise ValueError('Ports must be between 1 and 65535')
        if self.mode != 'local':
            self.address = validate_address(self.address)
            if self.port == self.backend_port or self.backend_port in {80, 443}:
                raise ValueError('Choose a separate internal port, other than 80/443')
            if self.mode == 'https' and self.port == 80:
                raise ValueError('HTTPS needs a separate port; port 80 is used for certificate validation')
        if self.email and not re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+', self.email):
            raise ValueError('Invalid certificate contact email')
        for value in (self.state, self.token_file):
            if not Path(value).is_absolute() or any(c in value for c in '\n\r\0'):
                raise ValueError('State and token paths must be absolute single-line paths')
        return self

    @property
    def internal_port(self):
        return self.port if self.mode == 'local' else self.backend_port

    @property
    def cert_name(self):
        return 'splitforge-' + hashlib.sha256(self.address.encode()).hexdigest()[:12]

    @property
    def url(self):
        host = '127.0.0.1' if self.mode == 'local' else self.address
        if ':' in host:
            host = f'[{host}]'
        scheme = 'https' if self.mode == 'https' else 'http'
        return f'{scheme}://{host}:{self.port}'


def validate_address(value: str) -> str:
    value = value.strip().rstrip('.')
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        try:
            value = value.encode('idna').decode('ascii').lower()
        except UnicodeError:
            raise ValueError('Invalid domain name') from None
        if len(value) > 253 or '.' not in value or not all(
            re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label) for label in value.split('.')
        ):
            raise ValueError('Enter a domain or public IP, without a scheme, path or port')
        return value
    if not address.is_global:
        raise ValueError('Public web access needs a globally routable IP')
    return str(address)


def load_settings() -> WebSettings | None:
    if not CONFIG.exists():
        return None
    if CONFIG.is_symlink() or CONFIG.stat().st_uid != 0 or CONFIG.stat().st_mode & 0o022:
        raise ValueError('Web configuration must be a root-owned file without group/world write access')
    return WebSettings(**json.loads(CONFIG.read_text())).validate()


def suggested_ip() -> str:
    data = json.loads(run(['ip', '-j', '-4', 'address', 'show', 'scope', 'global']).stdout)
    for interface in data:
        for entry in interface.get('addr_info', []):
            address = entry.get('local', '')
            if address and ipaddress.ip_address(address).is_global:
                return address
    return ''


def service_text(settings: WebSettings) -> str:
    # systemd supplies null stdin; omit the newer interactive-only override so
    # the same listener unit remains usable after rollback to web-capable 2.3.
    command = [sys.executable, '-m', 'splitforge', '--state', settings.state, 'web',
               '--host', '127.0.0.1', '--port', str(settings.internal_port), '--token-file', settings.token_file]
    return MARKER + f'''[Unit]
Description=SplitForge web control panel
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
StandardInput=null
ExecStart={' '.join(unit_word(word) for word in command)}
Restart=on-failure
RestartSec=3
UMask=0077
KillSignal=SIGINT
KillMode=mixed
TimeoutStopSec=30min

[Install]
WantedBy=multi-user.target
'''


def nginx_text(settings: WebSettings, *, challenge_only=False) -> str:
    """Validate public Host/Origin before normalizing the loopback upstream."""
    address = settings.address
    text = MARKER
    if settings.mode == 'https':
        text += f'''server {{
    listen 80;
    listen [::]:80;
    server_name {address};
    access_log off;
    location ^~ /.well-known/acme-challenge/ {{
        root {CHALLENGE};
        default_type text/plain;
        try_files $uri =404;
    }}
    location / {{ return 308 {settings.url}$request_uri; }}
}}
'''
    if challenge_only:
        return text
    internal = f'http://127.0.0.1:{settings.internal_port}'
    host = f'[{address}]' if ':' in address else address
    authority = f'{host}:{settings.port}'
    default_port = 443 if settings.mode == 'https' else 80
    hosts = f'"{authority}" 1;'
    if settings.port == default_port:
        hosts += f' "{host}" 1;'
    text += f'''map $http_host $sf_web_host_allowed {{ default 0; {hosts} }}
map $http_origin $sf_web_origin_allowed {{ default 0; "" 1; "{settings.url}" 1;'''
    if settings.port == default_port:
        text += f' "{settings.url.rsplit(":", 1)[0]}" 1;'
    text += f''' }}
map $http_origin $sf_web_backend_origin {{ default "{internal}"; "" ""; }}
server {{
    listen {settings.port}{' ssl' if settings.mode == 'https' else ''};
    listen [::]:{settings.port}{' ssl' if settings.mode == 'https' else ''};
    server_name {address};
    server_tokens off;
    access_log off;
    client_max_body_size 64k;
    if ($sf_web_host_allowed = 0) {{ return 421; }}
    if ($sf_web_origin_allowed = 0) {{ return 403; }}
'''
    if settings.mode == 'https':
        text += f'''    ssl_certificate /etc/letsencrypt/live/{settings.cert_name}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/{settings.cert_name}/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    error_page 497 =308 {settings.url}$request_uri;
'''
    text += f'''    location / {{
        proxy_pass {internal};
        proxy_set_header Host "127.0.0.1:{settings.internal_port}";
        proxy_set_header Origin $sf_web_backend_origin;
        proxy_set_header Connection "";
        proxy_http_version 1.1;
        proxy_cookie_flags sf_session {'secure ' if settings.mode == 'https' else ''}httponly samesite=strict;
        proxy_connect_timeout 5s;
        proxy_read_timeout 120s;
        proxy_redirect off;
    }}
}}
'''
    return text


def certificate_command(settings: WebSettings) -> list[str]:
    command = [str(CERTBOT), 'certonly', '--non-interactive', '--agree-tos', '--webroot',
               '--webroot-path', str(CHALLENGE), '--cert-name', settings.cert_name, '--keep-until-expiring',
               '--deploy-hook', 'systemctl reload nginx']
    command += ['--email', settings.email] if settings.email else ['--register-unsafely-without-email']
    try:
        ipaddress.ip_address(settings.address)
    except ValueError:
        command += ['--domain', settings.address]
    else:
        command += ['--required-profile', 'shortlived', '--ip-address', settings.address]
    return command


def ensure_tools(https: bool, report):
    if not shutil.which('nginx'):
        report('Installing nginx from the operating system repository…')
        run(['apt-get', 'update'], timeout=180)
        run(['env', 'DEBIAN_FRONTEND=noninteractive', 'apt-get', 'install', '-y', 'nginx', 'python3-venv'], timeout=300)
    if https:
        version = run([str(CERTBOT), '--version'], check=False).stdout if CERTBOT.exists() else ''
        match = re.search(r'(\d+)\.(\d+)', version)
        if not match or tuple(map(int, match.groups())) < (5, 4):
            report('Installing Certbot 5.4+ into its own environment…')
            run(['apt-get', 'update'], timeout=180)
            run(['env', 'DEBIAN_FRONTEND=noninteractive', 'apt-get', 'install', '-y', 'python3-venv'], timeout=300)
            run(['/usr/bin/python3', '-m', 'venv', str(CERTBOT.parent.parent)], timeout=120)
            run([str(CERTBOT.parent / 'pip'), 'install', '--upgrade', 'certbot>=5.4,<6'], timeout=300)


def nginx_reload():
    result = run(['nginx', '-t'], check=False)
    if result.returncode:
        raise RuntimeError('nginx configuration check failed: ' + result.stderr[-1500:])
    if run(['systemctl', 'is-active', '--quiet', 'nginx'], check=False).returncode == 0:
        run(['systemctl', 'reload', 'nginx'])
    else:
        run(['systemctl', 'start', 'nginx'])


def _backend_healthy(settings: WebSettings):
    import urllib.request
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for attempt in range(30):
        try:
            with opener.open(f'http://127.0.0.1:{settings.internal_port}/api/session', timeout=2) as response:
                data = json.load(response)
                if data.get('version') and not data.get('demo'):
                    return
        except (OSError, ValueError):
            pass
        time.sleep(0.25)
    raise RuntimeError('Panel did not become ready; inspect journalctl -u splitforge-web')


def _public_healthy(settings: WebSettings):
    import urllib.request
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    error = None
    for attempt in range(10):
        try:
            with opener.open(settings.url + '/api/session', timeout=3) as response:
                data = json.load(response)
                if data.get('version') and not data.get('demo'):
                    return
                error = ValueError('Unexpected service at the public address')
        except (OSError, ValueError) as failure:
            error = failure
        time.sleep(0.5)
    raise RuntimeError('Public panel verification failed; check address, listener and firewall: ' + str(error)) from error


def _check_internal_port(settings: WebSettings):
    try:
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', settings.internal_port))
    except OSError:
        import psutil
        result = run(['systemctl', 'show', '-p', 'MainPID', '--value', UNIT.name], check=False)
        pid = int(result.stdout.strip() or '0')
        listeners = [entry for entry in psutil.net_connections(kind='tcp')
                     if entry.status == 'LISTEN' and entry.laddr.port == settings.internal_port]
        if not pid or not listeners or any(entry.pid != pid for entry in listeners):
            raise ValueError(f'Internal port {settings.internal_port} belongs to another process; choose --backend-port') from None


def deploy(settings: WebSettings, *, agree_tos=False, report=print):
    """Commit owned files only after readiness; restore prior deployment on failure."""
    require_root()
    settings.validate()
    if settings.mode == 'https' and not agree_tos:
        raise ValueError('Certificate issuance requires --agree-tos (https://letsencrypt.org/repository/)')
    CONFIG.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (CONFIG.parent / '.web-setup.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Another web setup is running') from None
        _deploy(settings, report)


def _deploy(settings, report):
    _check_internal_port(settings)
    if UNIT.exists() and MARKER.strip() not in UNIT.read_text() and 'splitforge web' not in UNIT.read_text():
        raise ValueError('Refusing to replace an unrelated splitforge-web unit')
    for path in (NGINX, RENEW_SERVICE, RENEW_TIMER):
        if path.exists() and not path.read_text().startswith(MARKER):
            raise ValueError(f'Refusing to overwrite an unmanaged file: {path}')
    legacy = LEGACY_NGINX.exists()
    if legacy:
        source = LEGACY_NGINX.read_text()
        if not (source.startswith('map $http_origin $splitforge_origin_allowed {')
                and 'proxy_cookie_flags sf_session secure httponly samesite=strict;' in source):
            raise ValueError(f'Migrate the existing unmanaged proxy first: {LEGACY_NGINX}')
    managed = (CONFIG, UNIT, NGINX, RENEW_SERVICE, RENEW_TIMER, *([LEGACY_NGINX] if legacy else []))
    old = {path: (path.read_text(), path.stat().st_mode & 0o777) if path.exists() else None for path in managed}
    old_service = {unit: (run(['systemctl', 'is-active', '--quiet', unit], check=False).returncode == 0,
                          run(['systemctl', 'is-enabled', '--quiet', unit], check=False).returncode == 0)
                   for unit in (UNIT.name, RENEW_TIMER.name, 'nginx')}
    rules = []
    try:
        if settings.mode != 'local':
            ensure_tools(settings.mode == 'https', report)
            run(['nginx', '-t'])
        if old_service[UNIT.name][0]:
            report('Stopping the previous panel service after active operations finish…')
            run(['systemctl', 'stop', UNIT.name], timeout=1810)
        if legacy:
            backup = CONFIG.parent / ('legacy-nginx-' + str(time.time_ns()) + '.bak')
            atomic_secret(backup, LEGACY_NGINX.read_text())
            LEGACY_NGINX.unlink()
        if settings.mode != 'local':
            if shutil.which('ufw') and 'Status: active' in run(['ufw', 'status']).stdout:
                status = run(['ufw', 'status']).stdout
                for port in ({80, settings.port} if settings.mode == 'https' else {settings.port}):
                    if not re.search(rf'(?m)^{port}/tcp\s+ALLOW', status):
                        run(['ufw', 'allow', f'{port}/tcp', 'comment', 'SplitForge web'])
                        rules.append(port)
            if settings.mode == 'https':
                CHALLENGE.mkdir(parents=True, exist_ok=True, mode=0o755)
                os.chmod(CHALLENGE, 0o755)
                atomic_secret(NGINX, nginx_text(settings, challenge_only=True), 0o644)
                nginx_reload()
                report('Requesting a trusted certificate; public port 80 must reach this server…')
                result = run(certificate_command(settings), timeout=300, check=False)
                if result.returncode:
                    raise RuntimeError('Certificate issuance failed. Check DNS/public port 80. ' + result.stderr[-1800:])
            atomic_secret(NGINX, nginx_text(settings), 0o644)
            nginx_reload()
            if legacy:
                # The old IP-specific listening socket may need to become a wildcard socket.
                run(['systemctl', 'restart', 'nginx'])
            run(['systemctl', 'enable', 'nginx'])
        elif NGINX.exists() or legacy:
            NGINX.unlink(missing_ok=True)
            nginx_reload()
        from splitforge.web.server import read_token
        read_token(Path(settings.token_file))
        atomic_secret(UNIT, service_text(settings), 0o644)
        if settings.mode == 'https':
            atomic_secret(RENEW_SERVICE, MARKER + f'''[Unit]
Description=Renew SplitForge web certificate
After=network-online.target
[Service]
Type=oneshot
TimeoutStartSec=10min
ExecStart={CERTBOT} renew --non-interactive --cert-name {settings.cert_name} --deploy-hook "systemctl reload nginx"
''', 0o644)
            atomic_secret(RENEW_TIMER, MARKER + '''[Unit]
Description=Check SplitForge certificate renewal twice daily
[Timer]
OnCalendar=*-*-* 00,12:00:00
RandomizedDelaySec=30min
Persistent=true
[Install]
WantedBy=timers.target
''', 0o644)
        else:
            run(['systemctl', 'disable', '--now', RENEW_TIMER.name], check=False)
            RENEW_SERVICE.unlink(missing_ok=True)
            RENEW_TIMER.unlink(missing_ok=True)
        run(['systemctl', 'daemon-reload'])
        run(['systemctl', 'enable', UNIT.name])
        run(['systemctl', 'restart', UNIT.name])
        _backend_healthy(settings)
        if settings.mode != 'local':
            _public_healthy(settings)
        if settings.mode == 'https':
            run(['systemctl', 'enable', '--now', RENEW_TIMER.name])
        atomic_secret(CONFIG, json.dumps(asdict(settings), indent=2) + '\n')
    except BaseException:
        report('Setup failed; restoring the previous web deployment…')
        for path, previous in old.items():
            if previous:
                atomic_secret(path, previous[0], previous[1])
            else:
                path.unlink(missing_ok=True)
        run(['systemctl', 'daemon-reload'], check=False)
        for unit, (active, enabled) in old_service.items():
            run(['systemctl', 'enable' if enabled else 'disable', unit], check=False)
            run(['systemctl', 'restart' if active else 'stop', unit], check=False)
        for port in rules:
            run(['ufw', 'delete', 'allow', f'{port}/tcp'], check=False)
        raise
    report(f'Panel ready: {settings.url}')
    report(f'Access token file: {settings.token_file} (sudo cat; never share this token)')
    if settings.mode == 'local':
        report(f'Use SSH forwarding: ssh -N -L {settings.port}:127.0.0.1:{settings.port} USER@SERVER -p SSH_PORT')
    elif settings.mode == 'http':
        report('HTTP was selected: this address does not encrypt credentials or session cookies.')


def wizard(state: Path):
    import typer
    require_root()
    previous = load_settings()
    typer.echo('SplitForge web setup / راه‌اندازی پنل وب')
    public = typer.confirm('Public access without an SSH tunnel? / دسترسی مستقیم با IP یا دامنه؟', default=True)
    mode = 'local'
    address = ''
    email = ''
    agreement = False
    if public:
        mode = 'https' if typer.confirm('Enable SSL/HTTPS? / فعال‌کردن SSL؟', default=True) else 'http'
        kind = typer.prompt('Certificate/access target: domain or ip / دامنه یا آی‌پی', default='ip')
        if kind not in {'domain', 'ip'}:
            raise ValueError('Choose domain or ip')
        address = typer.prompt('Domain name' if kind == 'domain' else 'Public IP',
                               default=previous.address if previous and previous.address else suggested_ip() or None)
        address = validate_address(address)
        is_ip = False
        try:
            ipaddress.ip_address(address)
            is_ip = True
        except ValueError:
            pass
        if is_ip != (kind == 'ip'):
            raise ValueError('The address does not match the selected domain/IP target')
        if mode == 'https':
            email = typer.prompt('Certificate email (optional)', default='', show_default=False)
            agreement = typer.confirm('Accept Let’s Encrypt terms? https://letsencrypt.org/repository/', default=True)
            if not agreement:
                raise ValueError('Certificate setup cancelled; no deployment changes made')
    port = typer.prompt('Panel port / پورت پنل', default=previous.port if previous else 9090, type=int)
    settings = WebSettings(mode=mode, address=address, port=port, email=email, state=str(state))
    deploy(settings, agree_tos=agreement, report=typer.echo)
