# Web control panel

[English README](../README.md) · [راهنمای فارسی](README.fa.md) · [Security](../SECURITY.md)

SplitForge 2.3 adds a browser control plane styled like a macOS Terminal window:
traffic lights, a command prompt, a dark workspace and green/teal status details.
The networking engine still runs on Linux. Use any modern desktop browser on
macOS, Linux or Windows; a responsive layout supports narrow/mobile screens.

![Actual desktop panel with read-only sample data](assets/web-overview.png)

## Start on your VPS

```sh
sudo splitforge update
sudo splitforge web
```

The panel listens on `127.0.0.1:8765`. On first start it creates a random access
token in `/etc/splitforge/web.token`, mode 0600. Read it in another SSH terminal:

```sh
sudo cat /etc/splitforge/web.token
```

Keep the first terminal running. On your own computer, establish an SSH forward
to your VPS (replace the example hostname):

```sh
ssh -N -L 8765:127.0.0.1:8765 root@YOUR_VPS_HOST
```

Visit [http://127.0.0.1:8765](http://127.0.0.1:8765) in your local browser and
paste the token into the sign-in form. Use the same local/remote port; request
Host and Origin are checked. The panel intentionally rejects public binding
such as `--host 0.0.0.0`. Do not expose this root control plane through a public
port/proxy. The SSH connection encrypts traffic between your computer and VPS.

If `update` is unavailable in an older installation, bootstrap once with the
[manual upgrade procedure](GETTING_STARTED.md#replace-and-upgrade).

## Preview without root or credentials

```sh
splitforge web --demo
```

Click **Explore read-only demo**. It uses documentation IP addresses and sample
workloads. Forms and navigation work, but mutation requests are rejected; no
profiles, commands or downloads run. Installed-core detection and system-resource
readouts describe the local machine. Native macOS/Windows can preview this UI
after installing the Python package; actual network management requires Linux.

## What you can manage

| Page | Controls |
| --- | --- |
| Overview | Profile lifecycle, last exit/IP timing, shared tunnel transfer, running workloads and host main-route comparison |
| App router | Register scripts/binaries/services; browse server files; assign Direct or a profile; start, stop and remove |
| Tunnel profiles | URI/file imports, DNSTT/Slipstream wizard, replacement of stopped profiles, start, test, stop and remove |
| Security & DNS | Mandatory guard explanation; per-profile verified DoH URL/bootstrap settings |
| Core installer | Select components, automatically include proxy helpers, skip installed binaries, inspect individual results |
| Live logs | Follow the SplitForge systemd journal and recent operation messages |
| Quick start | Six-step English/Persian guide |

Keyboard 1–7 switches pages when focus is outside a form. On mobile, the menu
button opens the sidebar. Wide tables scroll within their panels. Escape closes
dialogs. Search filters app names/commands/users or profile names/protocols.

Profile import accepts a URI or a **path on the VPS**, not a browser-local file.
Use the server file browser or transfer provider files privately beforehand.
The browser never receives saved profile configs/private keys. Replacement needs
a fresh source and preserves the existing ID/assignments. DNSTT public keys are
hex; Slipstream's pinned certificate path must exist on the server.

For scripts, check the command, Linux account and working directory; use your
app's own Python venv when needed. Root is supported with the runner's existing
privilege hardening. A file choice does not move an existing process. Registering
does not start the workload: assign its route to start it. Switching routes is a
restart and loses open connections/process memory. Direct removes tunnel routing.

Stopping a profile can stop its dependent workloads. Reassign/remove all app
and user references before deleting it. Starting a profile does not automatically
restart every app stopped with it; use App Router deliberately.

## Jobs, refresh and failure behavior

Mutations run sequentially in a background worker and return a job ID immediately.
The UI polls state every three seconds. The operation banner and job messages
show progress; simultaneous mutations receive a busy response. DNS/core selection
forms are not reset by polling. Session expiry or logout requires signing in again.

Active unit state is not a fresh connectivity test; use **Test egress** after
starting a profile. Timing includes DNS/TLS/HTTPS/retries. Byte counters are shared
by all apps using a profile and reset when its interface is recreated. Host route
comparison checks the main IPv4 table against panel startup, not every SSH failure
mode or policy/firewall rule on the machine.

Core installs use the existing checksum-verified installer. An individual failure
does not remove successful installs, and remaining selected cores are attempted.
Reopen the checklist to retry missing items. Detection means an executable is on
PATH, not that its version or upstream connection is healthy. Source builds can
take several minutes. Closing a browser does not cancel a submitted operation.

Ctrl+C stops a foreground panel after waiting for the active operation. Managed
workloads continue running when the web panel exits. Job history and sessions are
in memory; restarting the panel clears them. Profile/app state remains on disk.

## Custom options

```sh
sudo splitforge --state /root/private/state.json web --port 9000 --token-file /root/private/web.token
```

Forward port 9000 to port 9000 in that case. Global `--state` precedes `web`.
Existing token files must be regular files owned by the server user, mode 0600,
containing 32–256 ASCII non-whitespace characters. A restart invalidates all
sessions. To rotate access, stop the panel, replace the file with a fresh random
token under those permissions, then restart it. The server does not print tokens
or place them in URLs/browser local storage.

## Optional persistent systemd service

Create `/etc/systemd/system/splitforge-web.service` with your editor:

```ini
[Unit]
Description=SplitForge local web control panel
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
ExecStart=/usr/local/bin/splitforge web --host 127.0.0.1 --port 8765
Restart=on-failure
RestartSec=3
UMask=0077
KillSignal=SIGINT
KillMode=mixed
TimeoutStopSec=30min

[Install]
WantedBy=multi-user.target
```

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now splitforge-web.service
sudo journalctl -u splitforge-web.service --no-pager -n 50
```

The initial stop signal goes to the Python server so it can finish a job before
exiting. Wait for jobs to finish before upgrades, then restart the web service
after updating the package. It remains bound to loopback; keep using SSH forwarding.

## Trust boundary and verification

An administrator token grants management authority over root workloads. Treat it
like an SSH credential. Sessions use HttpOnly/SameSite cookies, CSRF tokens,
Host/Origin checks and a bounded sign-in failure rate. Assets are packaged locally;
there are no external script/font/CDN dependencies. Responses disable caching and
framing. This is a local operator interface, not an audited public hosting service.

Tests cover HTTP auth/session expiry/logout, CSRF/origin/host rejection, demo
no-mutation behavior, request limits, secret filtering and serialized jobs. An
opt-in Linux test manages a real root systemd service via authenticated HTTP.
Playwright checks browser forms, file browsing, DNS edits surviving polling,
XSS escaping, logs, Persian help, mobile navigation and logout. See
[the validation record](VALIDATION.md) for commands and limits.
