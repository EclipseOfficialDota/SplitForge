# Installation and hands-on tutorial

[README](../README.md) · [فارسی](README.fa.md) · [Protocols](PROTOCOLS.md) · [Troubleshooting](TROUBLESHOOTING.md)

## Requirements

Linux with systemd as PID 1, Python 3.10+, `/dev/net/tun`, nftables, network
namespaces and root access. Ubuntu 22.04/24.04 and Debian 12/13 are installer
targets; restricted containers may deny required kernel operations. Native
Windows/macOS cannot run the engine. The recorded integration system is Ubuntu
24.04 under WSL2 with systemd. See [actual validation](VALIDATION.md).

Reserve `10.203.0.0/18`, routing tables 20001–24095 and priorities 12001–16095.
Review [resource ownership](ARCHITECTURE.md#owned-names-and-address-space)
against your VPN/container addressing and firewall. Host firewall managers can
still reject traffic that SplitForge's own table permits.

The operator uses root. Workloads can use root or existing ordinary accounts.
Root scripts can read `/root`; their capabilities are still removed. Choose
dedicated accounts when practical. Root programs must be trusted.

## Install

```sh
sudo apt-get update
sudo apt-get install -y git
git clone https://github.com/EclipseOfficialDota/SplitForge.git
cd SplitForge
sudo bash install.sh
sudo splitforge doctor
```

Installed resources: distribution tools (iproute2/nftables/procps/WireGuard/
OpenVPN/proxychains4); an isolated `/opt/splitforge/venv`; Python dependencies
constrained by `requirements.lock`; verified Xray/tun2socks binaries under
`/usr/local/bin`; a public launcher symlink. Private `/etc/splitforge` uses
directory mode 0700 and state mode 0600. Privileged helpers import the installed
package. The source and installation prefix must be administrator-controlled.

```sh
sudo bash install.sh --prefix /opt/splitforge
sudo bash install.sh --skip-proxy-cores
sudo splitforge dependencies list
sudo splitforge dependencies install slipstream-client
sudo splitforge dependencies install dnstt-client
```

`--skip-proxy-cores` skips Xray/tun2socks downloads only. DNSTT builds from
pinned, SHA-256-verified source. It uses Go 1.24.4+ or downloads a verified
isolated compiler; module checksum verification remains enabled. Registry or
GitHub filtering can block builds. Private failure diagnostics are saved to
`/var/log/splitforge-install.log`.

Set `SPLITFORGE_DOWNLOAD_CACHE` to a directory of pre-fetched official release
filenames to supply core/compiler/source artifacts offline. DNSTT source uses
its pinned revision as filename. The same hashes apply and symlinks are
rejected. This does not cache apt, pip or Go module dependencies.

## Terminal workflow

```sh
splitforge --demo
sudo splitforge
```

Demo mode is read-only and uses synthetic documentation addresses. Real mode
has six pages: Home, App Router, VPN Profiles, Add/Browse, Security/DNS and Logs.
Mouse or 1–6 switches pages; Tab/arrows/Enter navigate; A adds an app, N adds a
profile, C opens route selection, T tests active profiles, R refreshes and Q
exits. Escape closes dialogs. Recommended size: 120×40 or larger.

Closing the UI leaves supervised services running. Wait for in-progress
operations before exit. Active lifecycle is distinct from fresh egress health;
test a profile for a current result. Bandwidth is shared per-interface RX/TX,
not per-app billing, and resets with interface recreation. HTTPS timing includes
DNS/TLS/retries and is not ICMP ping.

### Popup tutorial and core checklist

Click **Quick start** in the sidebar or press **F1**. Use Back/Next to follow
the six lessons and the language button to choose English or فارسی. Close or
Escape dismisses it; opening/reading the guide never changes configuration.
The guide's **Core checklist** button takes you directly to core selection.

Press **F2**, use the sidebar **Core checklist** button, or open it from
**Logs & Tools**. Tick the needed cores, review the displayed plan, then choose
**Install selected**. Missing components needed by saved profiles are suggested;
with no profiles, the default suggestion is Xray/tun2socks. All required proxy
helpers and base network tools are included in the plan automatically.

Installed/missing means executable-path detection, not a version or connectivity
test. Installed items are skipped rather than updated. Use the CLI's explicit
`dependencies install NAME` to reinstall the pinned release when needed. Batch
progress is shown in Logs & Tools; builds/downloads run sequentially. DNSTT source
builds may take several minutes. A failed item is reported, remaining selected
items are attempted and successful installations remain installed. Reopen the
checklist to retry missing tools. Installation needs root and upstream network
access and does not start any profile. Demo mode allows preview only.

Actual read-only previews: [popup walkthrough](assets/guide.svg) and
[core checklist](assets/cores.svg). Terminal font/RTL support affects Persian
text rendering; English remains available in the guide.

## First tunnel

Keep real credentials under a mode-0700 directory, with files mode 0600, e.g.
`/root/splitforge-profiles/client.conf`. WireGuard needs an IPv4 Address and a
peer covering `0.0.0.0/0`. Provider lifecycle hooks are rejected.

```sh
sudo splitforge profile import /root/splitforge-profiles/client.conf --name wg-europe
sudo splitforge profile start wg-europe
sudo splitforge profile test wg-europe
sudo splitforge status
```

Import saves configuration without starting it. Start creates/enables the
profile unit and requires verified HTTPS egress plus DNS. Failure cleans up;
there is no direct fallback. Names or IDs select profiles.

For subscription URIs, avoid shell-history/process-list exposure by saving the
URI in a private file with your editor:

```sh
sudo splitforge profile import /root/splitforge-profiles/private.uri --uri-file --name proxy-europe
sudo splitforge profile import /root/splitforge-profiles/client.ovpn --name openvpn-europe
sudo splitforge profile import /root/splitforge-profiles/outbound.json --name xray-europe
```

Xray imports accept one outbound, without custom bypass routing/inbounds.
OpenVPN rejects scripts/plugins/includes. Referenced certificate/key files must
remain available; use [protocol-specific guidance](PROTOCOLS.md).

## Execute once

```sh
sudo splitforge exec --profile wg-europe --user root --cwd /root -- /usr/bin/python3 /root/bot.py
sudo splitforge exec --profile wg-europe --user www-data -- /usr/bin/curl https://example.com
sudo splitforge exec --profile direct --user root -- /usr/bin/id
```

Put `--` before the executable. Arguments are literal; use `/bin/sh -c` only
when deliberately requesting a shell. Use the application's own venv interpreter
when needed. CLI defaults to root; Python API defaults remain `nobody`.
`exec` waits and returns the command's exit code. It does not register a service.
Explicit Direct bypasses user mappings; an omitted profile can inherit one.

## Persistent apps and reassignment

```sh
sudo splitforge app add telegram-bot --user root --cwd /root/bot -- /root/bot/venv/bin/python /root/bot/main.py
sudo splitforge bind telegram-bot --profile wg-europe
sudo splitforge app list
sudo splitforge bind telegram-bot --profile proxy-europe
sudo splitforge bind telegram-bot --profile direct
sudo splitforge app stop telegram-bot
```

Registration does not launch the command. Bind creates/starts/enables a
`splitforge-app-<id>.service`, with restart-on-failure. `bind --stopped` saves
the assignment without starting it. Explicit app stop disables generated boot
intent. Reassignment stops the previous service, updates namespace properties
and restarts; startup failure attempts to restore the previous unit/assignment.
Application memory/connections and data transactions are not migrated/rolled back.

In the TUI, the process picker copies a command; it never moves the running
process. Stop the original yourself if duplicate instances would conflict.
File picking registers `.py`, `.sh` or executable binary commands; check their
account, interpreter, working directory and file permissions.

## Existing systemd services

```sh
sudo splitforge app add my-worker --user root --service my-worker.service
sudo splitforge bind my-worker --profile wg-europe
```

The service must be loaded and its effective user must match registration.
Absent `User=` and numeric `User=0` are root and are supported. Socket-activated
services, SplitForge internals, SSH aliases and host network/resolver services
are rejected. Existing service hardening can conflict with mounts; inspect its
effective configuration. The only owned drop-in is `90-splitforge.conf`.
Direct removes the drop-in and restarts the original service. Removal stops it
without deleting the original unit/data. Adopted boot enablement stays yours.

## Ordinary user managers

```sh
sudo splitforge user bind worker wg-europe
sudo splitforge user bind worker direct
```

This writes/removes a `user@UID.service` drop-in for UID >=1000. It affects
future systemd user workloads after a deliberate user-manager restart, which
interrupts that user's services. It does not capture existing shells, SSH,
cron/system services or every arbitrary UID process. Root-wide user-manager
binding is prohibited; route root commands/services individually.

## Encrypted DNS and private probes

```sh
sudo splitforge profile stop wg-europe
sudo splitforge profile dns wg-europe https://cloudflare-dns.com/dns-query 1.1.1.1
sudo splitforge profile start wg-europe
```

The bootstrap address must serve the configured hostname with a valid TLS
certificate. Resolver requests use `127.0.0.53` inside the namespace and travel
through the tunnel as HTTPS. DNS and kill-switch enforcement are mandatory in
shared tunnel namespaces. Application-specific resolvers still use that app's
namespace data path. IPv6 is disabled for this release.

For private environments, use an HTTPS trace endpoint returning `ip=<IPv4>` and
optionally `loc=<two-letter-country>` on separate lines:

```sh
sudo splitforge profile probe wg-europe --url https://probe.example.com/trace --tls-ca-file /root/private-ca.pem
```

Stop the profile first. The custom CA applies to both probe and DoH; keep it
available to root helpers. Omitting the CA option restores system trust. TLS
verification is never disabled. Default probe/DoH use Cloudflare, which sees
the tunnel's exit address when queried.

## Replace and upgrade

```sh
sudo splitforge profile stop wg-europe
sudo splitforge profile import /root/splitforge-profiles/new.conf --replace wg-europe
sudo splitforge profile start wg-europe
sudo splitforge bind telegram-bot --profile wg-europe
```

Replacement keeps the ID, subnet slot, app references, DNS and probe settings,
and clears old measurements. Stopping a profile stops dependent apps; starting
it does not automatically restart every app. Rebind or deliberately restore.

Securely back up `/etc/splitforge`, original credential files, application data
and owned units/drop-ins before upgrading:

```sh
git pull --ff-only
sudo bash install.sh --upgrade --restore
sudo splitforge status
```

Upgrade stops managed apps/profiles while preserving enabled intent, updates
the package and optionally restores it. Without `--restore`, use
`sudo splitforge restore` after inspection. Installation failure can leave
workloads stopped; repair/reinstall the previous revision and restore. This is
not transactional package/data rollback. Boot dependencies are generated, but
provider readiness and reboot recovery must be rehearsed on your own host.

## Logs, stop and remove

```sh
sudo splitforge logs --follow
sudo splitforge status --json
sudo splitforge app remove telegram-bot
sudo splitforge profile stop wg-europe
sudo splitforge profile remove wg-europe
```

Remove/reassign app and user references before deleting profiles. Teardown
removes owned namespaces/veths/policy rules/firewall tables and runtime secrets,
not unrelated network configuration. `stop-all` stops registered resources and
disables generated boot intent while retaining state. `stop-all --preserve`
retains intent for later restore.

For uninstall, first unbind user managers, remove adopted/managed app
registrations and remove profiles. Then remove the launcher symlink and chosen
installation prefix. Keep protected backups until no longer needed. Distribution
tools and upstream binaries can be shared; check before removing them. Review
remaining adopted-service boot enablement separately.

## Validation levels

See [VALIDATION.md](VALIDATION.md) for reproducible unit/UI checks and opt-in
privileged Linux integration. Routine tests need no provider credentials/root.
