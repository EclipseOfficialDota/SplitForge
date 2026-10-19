"""Bounded health checks and explicit repair of SplitForge-owned resources."""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

import psutil

from splitforge.core import dependencies
from splitforge.core.netns import require_root, run


def guard_valid(document: dict, profile) -> bool:
    """Reject output accepts other than the tunnel, loopback or the proxy relay."""
    entries = document.get('nftables', [])
    chains = {item['chain']['name']: item['chain'] for item in entries if 'chain' in item}
    if any(chains.get(name, {}).get('policy') != 'drop' or chains[name].get('hook') != name
           or chains[name].get('type') != 'filter' for name in ('input', 'output', 'forward')):
        return False
    tunnel = False
    for item in entries:
        rule = item.get('rule', {})
        if rule.get('chain') != 'output':
            continue
        if any(set(part) - {'match', 'accept', 'drop', 'reject', 'counter'} for part in rule.get('expr', [])):
            return False
        if not any('accept' in part for part in rule.get('expr', [])):
            continue
        matches = [part['match'] for part in rule['expr'] if 'match' in part and part['match'].get('op') == '==']
        interfaces = [match['right'] for match in matches if match.get('left') == {'meta': {'key': 'oifname'}}]
        if interfaces and all(interface in {'lo', profile.interface} for interface in interfaces):
            tunnel |= profile.interface in interfaces
            continue
        destination = any(match.get('left') == {'payload': {'protocol': 'ip', 'field': 'daddr'}}
                          and match.get('right') == profile.gateway for match in matches)
        port = any(match.get('left') in ({'payload': {'protocol': 'tcp', 'field': 'dport'}},
                                       {'payload': {'protocol': 'udp', 'field': 'dport'}})
                   and match.get('right') == 1080 for match in matches)
        if not destination or not port or profile.protocol in {'wireguard', 'openvpn'}:
            return False
    return tunnel


def namespace_checks(manager, profile) -> list[tuple[str, bool, str]]:
    namespace = manager.netns
    result = namespace.command(profile, 'nft', '-j', 'list', 'table', 'inet', 'splitforge', check=False, timeout=5)
    try:
        guarded = result.returncode == 0 and guard_valid(json.loads(result.stdout), profile)
    except (ValueError, KeyError, TypeError):
        guarded = False
    dns = Path('/etc/netns', profile.namespace)
    resolver = dns / 'resolv.conf'
    nss = dns / 'nsswitch.conf'
    private_dns = (resolver.is_file() and [line.split('#', 1)[0].strip() for line in resolver.read_text().splitlines()
                   if line.split('#', 1)[0].strip().startswith('nameserver')] == ['nameserver 127.0.0.53'])
    private_dns = private_dns and nss.is_file() and 'hosts: files dns' in nss.read_text().splitlines()
    routes = namespace.command(profile, 'ip', '-j', '-4', 'route', 'show', 'default', check=False, timeout=5)
    try:
        rows = json.loads(routes.stdout)
        routed = routes.returncode == 0 and bool(rows) and all(row.get('dev') == profile.interface for row in rows)
    except (ValueError, TypeError):
        routed = False
    host_guard = run(['nft', 'list', 'table', 'inet', f'sf_{profile.id}'], check=False, timeout=5).returncode == 0
    return [('firewall', guarded and host_guard, 'Namespace/host guard is missing or allows an unexpected path.'),
            ('dns', private_dns, 'Namespace DNS files do not enforce the local encrypted-DNS stub.'),
            ('route', routed, 'Namespace default route does not exclusively use its tunnel interface.')]


def diagnose(store, manager, runner, *, repair=False, report=print, route_baseline=None):
    require_root()
    rows = []
    def record(category, scope, ok, message, remedy='', *, repaired=False, level='error'):
        row = {'category': category, 'scope': scope, 'status': 'ok' if ok else level,
               'message': message, 'remedy': '' if ok else remedy, 'repaired': repaired}
        rows.append(row)
        report(f'{category} · {scope}: {row["status"]} · {message}')
    profiles = store.profiles()
    apps = store.apps()
    unhealthy = set()
    desired = {app.profile_id for app in apps if app.enabled and app.profile_id} | set(store.snapshot()['users'].values())
    record('platform', 'systemd', Path('/proc/1/comm').read_text().strip() == 'systemd',
           'Check whether systemd is PID 1.', 'Use a VPS/VM with systemd enabled.')
    record('platform', 'TUN', Path('/dev/net/tun').exists(), 'Check the kernel TUN device.',
           'Ask the VPS provider to enable /dev/net/tun; load the tun module when supported.')
    required = {'base'}
    for profile in profiles:
        required.update({'wireguard'} if profile.protocol == 'wireguard' else {'openvpn'} if profile.protocol == 'openvpn'
                        else dependencies.component_plan(['dnstt-client' if profile.protocol == 'dnstt' else
                             'slipstream-client' if profile.protocol == 'slipstream' else 'xray']))
    for name in sorted(required):
        installed = dependencies.component_installed(name)
        fixed = False
        if not installed and repair:
            try:
                report(f'Installing required component: {name}')
                report(dependencies.install(name, progress=report))
                fixed = installed = dependencies.component_installed(name)
            except Exception as error:
                report(f'Component repair failed: {name}: {str(error)[:300]}')
        record('core', name, installed, 'Required component is installed.' if installed else 'Required component is missing.',
               f'Use Core installer to install {name}; inspect its individual download result.', repaired=fixed)
    for profile in profiles:
        try:
            status = manager.status(profile.id)
            wanted = profile.id in desired or run(['systemctl', 'is-enabled', '--quiet', f'splitforge-profile-{profile.id}.service'],
                                                    check=False, timeout=5).returncode == 0
            if not wanted and not status['active'] and not status['namespace']:
                record('tunnel', profile.name, True, 'Intentionally stopped; no repair was attempted.')
                continue
            checks = namespace_checks(manager, profile) if status['namespace'] else []
            healthy = status['active'] and status['namespace'] and all(ok for _, ok, _ in checks)
            fixed = False
            if not healthy and repair:
                # Stop bound processes before rebuilding a broken guard/DNS/route. Never select Direct.
                report(f'Rebuilding {profile.name}; managed workloads will restart and open connections will close.')
                manager.stop(profile.id)
                manager.start(profile.id)
                checks = namespace_checks(manager, profile)
                status = manager.status(profile.id)
                fixed = healthy = status['active'] and status['namespace'] and all(ok for _, ok, _ in checks)
                if healthy:
                    for app in apps:
                        if app.enabled and app.profile_id == profile.id:
                            runner.bind(app.id, profile.id, preserve_failover=True)
            record('tunnel', profile.name, healthy, 'Tunnel lifecycle and namespace checks passed.' if healthy else
                   'Tunnel is unavailable or its isolated network configuration is inconsistent.',
                   'Check required cores/provider configuration; use repair to rebuild only this managed tunnel.', repaired=fixed)
            if not healthy:
                unhealthy.add(profile.id)
            for category, ok, failure in checks:
                record(category, profile.name, ok, 'Managed namespace configuration passed.' if ok else failure,
                       'Repair rebuilds this managed namespace and restarts its enabled applications.', repaired=fixed and ok)
            if healthy:
                try:
                    outcome = manager.test(profile.id, persist=False)
                    record('dns-egress', profile.name, True, f'Fresh namespace HTTPS/DNS probe passed; exit {outcome["exit_ip"]}.')
                except Exception:
                    record('dns-egress', profile.name, False, 'Namespace DNS/HTTPS egress probe failed; no Direct fallback used.',
                           'Check provider reachability, DNS-over-HTTPS/bootstrap settings, remote credentials and MTU.')
        except Exception as error:
            unhealthy.add(profile.id)
            record('tunnel', profile.name, False, f'Check/repair failed: {str(error)[:300]}',
                   'Inspect Live logs and provider configuration. SSH and host routing were not repaired or reset.')
    for app in apps:
        if app.enabled:
            if app.profile_id in unhealthy:
                record('application', app.name, False, 'Workload repair is blocked until its assigned tunnel is healthy.',
                       'Repair the tunnel first; the assignment is retained and Direct is never selected automatically.')
                continue
            try:
                running = runner.running(app)
                fixed = False
                if repair and not running:
                    runner.bind(app.id, app.profile_id, preserve_failover=True)
                    fixed = running = runner.running(app)
                record('application', app.name, running, 'Enabled workload is running.' if running else 'Enabled workload is stopped.',
                       'Inspect the application journal, executable path, Linux user and working directory.', repaired=fixed)
            except Exception as error:
                record('application', app.name, False, f'Workload check failed: {str(error)[:300]}', 'Inspect its systemd journal.')
    try:
        result = run(['getent', 'ahostsv4', 'cloudflare-dns.com'], check=False, timeout=6)
        record('dns', 'host', result.returncode == 0 and bool(result.stdout.strip()), 'Check host DNS resolution.',
               'Inspect resolvectl status / host resolver settings; repair does not replace host DNS.')
    except Exception:
        record('dns', 'host', False, 'Host resolver timed out.', 'Inspect host resolver settings and outbound DNS connectivity.')
    try:
        from splitforge.web.setup import load_settings, nginx_reload
        settings = load_settings()
        if settings:
            if repair and settings.mode != 'local':
                nginx_reload()
            ports = {entry.laddr.port for entry in psutil.net_connections(kind='tcp') if entry.status == 'LISTEN'}
            for port in {settings.internal_port, settings.port}:
                record('port', str(port), port in ports, 'Check configured web listener.',
                       'Inspect splitforge-web/nginx journal and rerun splitforge web setup; this worker cannot restart itself.')
            if settings.mode == 'https':
                timer = run(['systemctl', 'is-active', '--quiet', 'splitforge-web-renew.timer'], check=False).returncode == 0
                if repair and not timer:
                    run(['systemctl', 'enable', '--now', 'splitforge-web-renew.timer'])
                    timer = run(['systemctl', 'is-active', '--quiet', 'splitforge-web-renew.timer'], check=False).returncode == 0
                record('certificate', 'renewal', timer, 'Check certificate renewal timer.', 'Rerun web setup to restore renewal scheduling.')
        else:
            record('port', 'web', False, 'No setup-managed web configuration; current backend remains reachable.',
                   'Run splitforge web setup for public listener and certificate diagnostics.', level='warning')
        if shutil.which('ufw'):
            active = 'Status: active' in run(['ufw', 'status'], timeout=6).stdout
            record('firewall', 'UFW', True, 'UFW active; inspect allow rules for public ports.' if active else 'UFW inactive; other host/provider policies may apply.')
        record('firewall', 'provider', False, 'External/cloud firewall reachability requires an independent public connection.',
               'Allow the configured panel port and HTTP-01 port 80 at the provider; host checks cannot prove provider rules.', level='warning')
    except Exception as error:
        record('web', 'setup', False, f'Web configuration check failed: {str(error)[:300]}', 'Inspect nginx configuration and web setup output.')
    current = run(['ip', '-j', '-4', 'route', 'show', 'table', 'main'], timeout=5).stdout
    if route_baseline is not None:
        record('routing', 'host', current == route_baseline, 'Compare the host main route with the panel startup baseline.',
               'Inspect changes by other network tools; repair deliberately does not reset host routes.')
    return {'updated': time.time(), 'repair': repair, 'checks': rows,
            'errors': sum(row['status'] == 'error' for row in rows),
            'warnings': sum(row['status'] == 'warning' for row in rows)}
