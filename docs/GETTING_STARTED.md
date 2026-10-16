# Hands-on backend tutorial

[Home](../README.md) · [فارسی](README.fa.md) · [Protocols](PROTOCOLS.md) ·
[Troubleshooting](TROUBLESHOOTING.md)

This guide uses the **current Part 1 Python API**. Examples target a disposable
Ubuntu/Debian VPS or VM with systemd. Linux integration testing is pending;
these instructions are a developer lab workflow, not a certified deployment.
No command in this document was executed on your VPS while writing it.

## Contents

1. [Requirements](#requirements)
2. [Validation levels](#validation-levels)
3. [Manual Linux lab setup](#manual-linux-lab-setup)
4. [First WireGuard profile](#first-wireguard-profile)
5. [One-off execution](#one-off-execution)
6. [Persistent Python application](#persistent-python-application)
7. [Reassignment and Direct mode](#reassignment-and-direct-mode)
8. [Existing systemd services](#existing-systemd-services)
9. [User-manager binding](#user-manager-binding)
10. [Inspection, stop and cleanup](#inspection-stop-and-cleanup)
11. [Updating](#updating-the-manual-installation)

## Requirements

| Requirement | Reason |
| --- | --- |
| Linux with root/sudo | Namespace, nftables and system service mutations are privileged |
| Python 3.10+ | Conservative development baseline for the source |
| systemd as PID 1 | Runner and profile lifecycle create system services |
| Modern systemd; 249+ suggested for the lab | Namespace, transient-service and credential features are used |
| `/dev/net/tun` and network namespace support | Provider/container restrictions can prevent their use |
| Kernel WireGuard support for WireGuard profiles | Tools alone do not supply every kernel capability |
| Working upstream configuration | SplitForge does not supply a subscription or remote server |
| Non-root workload account | The runner rejects UID 0 |
| Provider console for recovery | Tests do not certify SSH behavior |

Ubuntu 22.04/24.04 and Debian 12 are reasonable **lab targets**, not certified
platforms. Native Windows/macOS, restricted containers, and WSL without suitable
systemd/kernel capabilities cannot be assumed to run the networking backend.

```sh
python3 --version
ps -p 1 -o comm=
systemd --version
uname -r
test -c /dev/net/tun && echo 'TUN device available'
```

Do not prepare the machine by replacing its default route, globally activating
a VPN, or flushing an existing firewall. The backend's owned resources are
described in [Architecture](ARCHITECTURE.md).

## Validation levels

The recorded Windows run passed nine checks and skipped the POSIX state test.
They cover URI parsing, forbidden directives, argument escaping, command scope
and guard generation. The POSIX test exercises state persistence/references.

| Level | Establishes | Current evidence |
| --- | --- | --- |
| Unit/parser checks | Python logic and selected generated commands | Recorded local run |
| Root Linux integration | Real namespaces, nftables, interfaces and systemd | Pending |
| Protocol interoperability | Real connections to configured upstreams | Pending |
| Failure testing | Kill switch, DNS, restart and rollback behavior | Pending |
| Reboot/upgrade testing | Persistent units recover correctly | Pending |

The first row does not establish the others. Run the checks without root:

```sh
git clone https://github.com/EclipseOfficialDota/SplitForge.git
cd SplitForge
python3 -m unittest discover -s tests -v
```

## Manual Linux lab setup

There is no public CLI or package metadata yet. This temporary setup copies the
stdlib-only backend into a stable root-owned Python virtual environment so
systemd can import helpers after your shell exits.

### 1. Install distribution tools

```sh
sudo apt-get update
sudo apt-get install --no-install-recommends \
  python3 python3-venv git ca-certificates curl \
  iproute2 nftables procps

# Install the adapters you plan to exercise:
sudo apt-get install --no-install-recommends wireguard-tools openvpn

# Optional TCP fallback wrapper:
sudo apt-get install --no-install-recommends proxychains4
```

Proxy profiles additionally need `xray` and `tun2socks`; DNSTT needs
`dnstt-client`, and Slipstream needs `slipstream-client`. Download/build them
from the official projects linked in [Protocols](PROTOCOLS.md). Match CPU
architecture and verify the upstream integrity information. Versions are not
pinned here, and matching CLI/configuration formats must be checked.

Place binaries in a root-controlled system path such as `/usr/local/bin`.
Aliases and login-shell-only PATH changes are not sufficient for systemd.
No global nftables service activation or host firewall replacement is required
by these instructions.

### 2. Deploy a stable source copy

The following source and venv paths must be new for first-time setup:

```sh
sudo install -d -m 0755 /opt/splitforge
sudo git clone https://github.com/EclipseOfficialDota/SplitForge.git /opt/splitforge/source
sudo python3 -m venv /opt/splitforge/venv

sudo /opt/splitforge/venv/bin/python - <<'PY'
import shutil
import sysconfig
from pathlib import Path

source = Path('/opt/splitforge/source/splitforge')
target = Path(sysconfig.get_paths()['purelib']) / 'splitforge'
if target.exists():
    raise SystemExit('Package exists; follow the update section instead.')
shutil.copytree(source, target)
print('Installed backend:', target)
PY
```

There are no third-party Python imports in the present backend. The planned
Textual/Rich/Typer distribution does not exist yet, and `pip install .` cannot
replace the manual copy while package metadata is absent.

Verify importability outside the checkout:

```sh
cd /tmp
sudo /opt/splitforge/venv/bin/python -c \
  'import splitforge; print(splitforge.__file__)'
```

The printed path should be in venv site-packages. Keep the interpreter at this
absolute path; generated profile units record `sys.executable`.

### 3. Create a workload account

```sh
sudo useradd --system --create-home \
  --home-dir /var/lib/splitforge-demo \
  --shell /usr/sbin/nologin splitforge-demo
sudo install -d -m 0755 /srv/splitforge-demo
sudo install -d -m 0700 /root/splitforge-profiles
```

Inspect an existing demo account instead of recreating it. Securely place a
genuine WireGuard configuration at `/root/splitforge-profiles/client.conf`:

```sh
sudo chmod 0600 /root/splitforge-profiles/client.conf
```

Private profile files should stay outside this Git repository. Imports copy
secrets into state; do not paste private URIs into shell history or public Issues.

## First WireGuard profile

The file needs an IPv4 `Address` and a peer with `AllowedIPs = 0.0.0.0/0`.
Hooks, `Table` and `SaveConfig` are rejected. Its `DNS` setting is replaced by
SplitForge's namespace-local DoH resolver.

```sh
sudo /opt/splitforge/venv/bin/python - <<'PY'
from splitforge.state import StateStore
from splitforge.protocols.manager import ProtocolManager

store = StateStore()
manager = ProtocolManager(store)
existing = [p for p in store.profiles() if p.name == 'wg-lab']
profile = existing[0] if existing else manager.import_profile(
    '/root/splitforge-profiles/client.conf', name='wg-lab'
)
print('Profile ID:', profile.id)
print('Missing tools:', manager.missing(profile.protocol))
manager.start(profile.id)
print('Egress:', manager.test(profile.id))
print('Lifecycle:', manager.status(profile.id))
PY
```

`start()` creates and enables the persistent profile boot unit and runs a live
DNS/HTTPS check. Failure triggers teardown attempts. Inspect journals if any
resource remains after failure.

`test()` contacts `https://www.cloudflare.com/cdn-cgi/trace` from the namespace.
It extracts the observed IPv4 address and country code. `latency_ms` includes
retries, DNS, TLS and HTTP: it is not ICMP or server-only latency. Success proves
reachability to that endpoint at that moment, not every destination/protocol.

`status()['active']` reflects the systemd profile unit, not a fresh upstream
reachability test. Stored exit IP and latency can be stale.

## One-off execution

Run one HTTPS request as the non-root demo user:

```sh
sudo /opt/splitforge/venv/bin/python - <<'PY'
from splitforge.state import StateStore
from splitforge.protocols.manager import ProtocolManager
from splitforge.core.runner import Runner

store = StateStore()
runner = Runner(store, ProtocolManager(store))
command = [
    '/usr/bin/python3', '-c',
    "import urllib.request; "
    "o=urllib.request.build_opener(urllib.request.ProxyHandler({})); "
    "print(o.open('https://www.cloudflare.com/cdn-cgi/trace', timeout=10).read().decode())"
]
raise SystemExit(runner.execute(
    command, profile_name='wg-lab', user='splitforge-demo', cwd='/tmp'
))
PY
```

This uses a transient service and returns the wrapper's exit status, without
creating a persistent app record. Interactive execution uses systemd PTY mode
when stdin/stdout are terminals; otherwise the wrapper uses pipe mode.

For your own scripts, explicitly select the interpreter:

```python
runner.execute(
    ['/usr/bin/python3', '/srv/my-app/worker.py'],
    profile_name='wg-lab', user='my-app-user', cwd='/srv/my-app'
)
runner.execute(
    ['/bin/sh', '/srv/my-app/job.sh'],
    profile_name='wg-lab', user='my-app-user', cwd='/srv/my-app'
)
```

The account must already exist and have appropriate file/directory permissions.
A file under `/root` normally needs relocation to a readable application path.
No shell is inserted for ordinary argument arrays.

If `profile_name` is omitted, `execute()` consults the saved mapping for its
`user`. Without a mapping it uses the host network. There is no explicit
one-off Direct override that bypasses an existing user mapping in this version.

## Persistent Python application

Create an egress-reporting demo:

```sh
sudo tee /srv/splitforge-demo/egress.py >/dev/null <<'PY'
import time
import urllib.request

opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
while True:
    try:
        with opener.open('https://www.cloudflare.com/cdn-cgi/trace', timeout=10) as response:
            print(response.read().decode(), flush=True)
    except Exception as error:
        print(type(error).__name__, str(error), flush=True)
    time.sleep(60)
PY
sudo chmod 0644 /srv/splitforge-demo/egress.py
```

Register the command and generate/start its unit:

```sh
sudo /opt/splitforge/venv/bin/python - <<'PY'
from splitforge.state import AppBinding, StateStore
from splitforge.protocols.manager import ProtocolManager
from splitforge.core.runner import Runner

store = StateStore()
runner = Runner(store, ProtocolManager(store))
existing = [a for a in store.apps() if a.name == 'egress-demo']
app = existing[0] if existing else AppBinding(
    name='egress-demo',
    argv=['/usr/bin/python3', '/srv/splitforge-demo/egress.py'],
    user='splitforge-demo', cwd='/srv/splitforge-demo',
)
store.save_app(app)
app = runner.bind(app.id, 'wg-lab')
print('App ID:', app.id)
print('Unit:', runner.unit(app))
PY
```

`save_app()` alone does not start anything. `bind()` writes the unit, starts it
by default and enables a generated app service for boot. With `start=False`,
it records/writes the assignment but leaves the app stopped and disables that
generated app unit. Use the printed unit with `systemctl status` or `journalctl`.

## Reassignment and Direct mode

Import a second real profile as `vless-lab` using [Protocols](PROTOCOLS.md), then:

```sh
sudo /opt/splitforge/venv/bin/python - <<'PY'
from splitforge.state import StateStore
from splitforge.protocols.manager import ProtocolManager
from splitforge.core.runner import Runner

store = StateStore()
runner = Runner(store, ProtocolManager(store))
app = next(a for a in store.apps() if a.name == 'egress-demo')
runner.bind(app.id, 'vless-lab')
PY
```

The destination profile is started, the app is stopped, the managed unit changes,
and the app starts again. Existing sockets and in-memory state are lost. Failure
triggers attempted restoration of the previous unit/state/running status, but
rollback can itself fail. Inspect actual service state after an exception.

To put this registered app on Direct instead, replace the final call with:

```python
runner.bind(app.id, None)
```

A generated app then runs in the host namespace. For an adopted service this
removes the owned drop-in and restores its original configuration. Direct has no
SplitForge namespace/DNS guard; original service isolation still applies if any.

## Existing systemd services

The service must already be loaded, have explicit non-root `User=`, and not be
socket activated. Root services and internal `splitforge-`/`user@` units are
rejected by this path. For `my-worker.service` with `User=my-worker`:

```python
app = AppBinding(name='my-worker', service='my-worker.service', user='my-worker')
store.save_app(app)
runner.bind(app.id, 'wg-lab')
```

The backend adds `/etc/systemd/system/my-worker.service.d/90-splitforge.conf`
and restarts the service. It preserves the base unit but adds namespace,
resolver and privilege restrictions. Those restrictions can affect applications
requiring capabilities. The service's existing enable/disable policy is not
owned by the runner. Removing its registration stops it and removes the owned
drop-in; it does not automatically start the original service again.

## User-manager binding

This advanced path requires a real account with UID >= 1000. Use a disposable
lab account, not the system demo user created above:

```python
unit = runner.bind_user('labuser', 'wg-lab')
print(unit)
```

The method writes a drop-in for `user@UID.service` and reloads systemd. It does
not restart the manager. Applying it to a running manager requires a deliberate
restart of the printed unit, potentially terminating its managed workloads.
It does not move existing SSH sessions, ordinary processes, cron jobs or system
services merely because they have the same UID. Future processes outside that
user manager are not intercepted either.

Remove the mapping/drop-in with:

```python
runner.bind_user('labuser', None)
```

A running manager needs a deliberate restart before its namespace changes.

## Inspection, stop and cleanup

List IDs without dumping configuration secrets:

```sh
sudo /opt/splitforge/venv/bin/python - <<'PY'
from splitforge.state import StateStore

store = StateStore()
for profile in store.profiles():
    print('PROFILE', profile.id, profile.name, profile.protocol, profile.namespace)
for app in store.apps():
    print('APP', app.id, app.name, app.profile_id, app.enabled)
PY
```

In the initialized privileged API context, stop the demo while keeping its
assignment, or remove its managed unit/registration:

```python
runner.stop(app.id)
# Alternatively, for permanent app deregistration:
runner.remove(app.id)
```

After removing/reassigning every app/user reference to the profile:

```python
profile = store.profile('wg-lab')
manager.stop(profile.id)
```

Stopping disables the profile boot unit, stops owned core services and attempts
to destroy its namespace, veth, owned route/rule and firewall table. `BindsTo=`
may stop bound apps too; their saved `enabled` flag is not a live state report.
Starting a profile again does not automatically restart every previously stopped
app: explicitly restart/rebind the workloads.

For permanent profile deletion, first remove the **specific stopped profile
unit**, then remove state so no boot helper points at a missing profile:

```python
from pathlib import Path
from splitforge.core.netns import run

unit_path = Path('/etc/systemd/system') / f'splitforge-profile-{profile.id}.service'
unit_path.unlink(missing_ok=True)
run(['systemctl', 'daemon-reload'])
store.delete_profile(profile.id)
```

Run this only after `manager.stop()`, with no remaining app/user references.
Deleting state alone does not tear down networking. Keep credentials/state until
teardown is complete. Do not flush unrelated routes or firewall rules.

## Updating the manual installation

There is no automated updater/schema migrator. Stop affected apps, unbind and
deliberately restart lab user managers, and stop their profiles. Back up private
state and external OpenVPN credentials with root-only permissions.

Fetch/review your chosen source revision. The venv holds a **copy**: updating the
checkout alone does not change the installed package. Replace only the installed
`splitforge` package after shutdown, retaining the absolute interpreter path.
Re-run tests, import-test from `/tmp`, then start/test a profile before restarting
its apps. Validate reboot recovery on the lab host before depending on it.
