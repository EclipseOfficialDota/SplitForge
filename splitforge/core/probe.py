"""Read-only egress checks in a running workload's pinned network/mount namespaces."""
from __future__ import annotations

import contextlib
import ipaddress
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from splitforge.core.netns import require_root, run


SCRIPT = '''
import ipaddress,json,socket,ssl,sys,urllib.request
from pathlib import Path
from urllib.parse import urlsplit
url,ca = sys.argv[1:]
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise ValueError("Probe redirects are disabled")
servers = [line.split()[1] for line in Path('/etc/resolv.conf').read_text().splitlines()
           if line.split() and line.split()[0] == 'nameserver' and len(line.split()) > 1][:8]
addresses = sorted({row[4][0] for row in socket.getaddrinfo(urlsplit(url).hostname,443,
                     family=socket.AF_INET,type=socket.SOCK_STREAM)})
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect(),
    urllib.request.HTTPSHandler(context=ssl.create_default_context(cafile=ca or None)))
with opener.open(url,timeout=8) as response:
    data = dict(line.split('=',1) for line in response.read(8192).decode().splitlines() if '=' in line)
print(json.dumps({'exit_ip':str(ipaddress.ip_address(data['ip'])),
    'dns_servers':servers,'resolved_addresses':addresses,'connectivity':True,
    'network_namespace':Path('/proc/self/ns/net').stat().st_ino,
    'mount_namespace':Path('/proc/self/ns/mnt').stat().st_ino}))
'''


def test_application(runner, app_id):
    require_root()
    app = runner.store.app(app_id)
    profile = runner.store.profile(app.profile_id) if app.profile_id else None
    if not runner.running(app):
        raise ValueError('Start the application before testing its actual route')

    def main_pid():
        value = run(['systemctl', 'show', runner.unit(app), '-p', 'MainPID', '--value'], timeout=5).stdout.strip()
        if not value.isdecimal() or int(value) <= 1:
            raise RuntimeError('Application has no running main process')
        return int(value)

    pid = main_pid()
    proc = Path('/proc', str(pid))
    # A chroot requires a separately installed probe interpreter/CA environment.
    # Refuse it instead of testing the host filesystem's DNS configuration.
    if not os.path.samefile(proc / 'root', '/'):
        raise ValueError('Route testing for chroot/RootDirectory services is not supported')
    identity = proc.joinpath('stat').read_text().rsplit(') ', 1)[1].split()[19]
    uid = runner._identity(app.user).pw_uid
    status = dict(line.split(':', 1) for line in proc.joinpath('status').read_text().splitlines() if ':' in line)
    if int(status['Uid'].split()[1]) != uid:
        raise ValueError('Running application user does not match its registration')
    gid = int(status['Gid'].split()[1])
    expected = Path('/run/netns', profile.namespace) if profile else Path('/proc/1/ns/net')
    start = time.monotonic()
    with contextlib.ExitStack() as stack:
        handles = []
        for kind in ('net', 'mnt'):
            fd = os.open(proc / 'ns' / kind, os.O_RDONLY | os.O_CLOEXEC)
            stack.callback(os.close, fd)
            handles.append(fd)
        if not expected.exists() or os.fstat(handles[0]).st_ino != expected.stat().st_ino:
            raise ValueError('Actual application namespace differs from its saved route; repair the assignment')
        if main_pid() != pid or proc.joinpath('stat').read_text().rsplit(') ', 1)[1].split()[19] != identity:
            raise RuntimeError('Application restarted during route inspection; retry')
        command = ['nsenter', f'--net=/proc/self/fd/{handles[0]}', f'--mount=/proc/self/fd/{handles[1]}',
                   '--', 'setpriv', '--no-new-privs', '--bounding-set=-all', '--inh-caps=-all', '--ambient-caps=-all',
                   f'--reuid={uid}', f'--regid={gid}', '--clear-groups', '--', sys.executable, '-I', '-c', SCRIPT,
                   profile.probe_url if profile else 'https://www.cloudflare.com/cdn-cgi/trace',
                   profile.tls_ca_file or '' if profile else '']
        result = subprocess.run(command, pass_fds=handles, capture_output=True, text=True, timeout=18,
                                cwd='/', env={'PATH': '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin', 'LANG': 'C.UTF-8'})
        if result.returncode:
            raise RuntimeError('Application HTTPS/DNS test failed in its actual namespaces; no host fallback was used')
        response = json.loads(result.stdout)
        if (response['network_namespace'] != os.fstat(handles[0]).st_ino
                or response['mount_namespace'] != os.fstat(handles[1]).st_ino):
            raise RuntimeError('Probe did not enter the application namespaces')
    if (main_pid() != pid or runner.store.app(app_id) != app or not runner.running(app)
            or proc.joinpath('stat').read_text().rsplit(') ', 1)[1].split()[19] != identity):
        raise RuntimeError('Application stopped, restarted or changed route during the test; retry')
    ipaddress.ip_address(response['exit_ip'])
    if profile and response['dns_servers'] != ['127.0.0.53']:
        raise RuntimeError('Application DNS differs from the isolated tunnel resolver')
    return dict(response, app_id=app.id, pid=pid, profile_id=app.profile_id, checked_at=time.time(),
                latency_ms=round((time.monotonic() - start) * 1000, 1),
                measurement='HTTPS and DNS in the running process network/mount namespaces')
