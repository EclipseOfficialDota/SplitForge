# Validation record and reproducible checks

[README](../README.md) · [Setup](GETTING_STARTED.md) · [Architecture](ARCHITECTURE.md)

Recorded during development on 2026-10-16 through 2026-10-19. These are actual results,
not an external audit, performance benchmark or universal production certificate.
GitHub CI has its own independently visible run status.

Initial local suite: **31 tests passed, zero skipped**, with
`SPLITFORGE_INTEGRATION=1` (22.858 seconds). The same suite without opt-in
skips the three privileged integration methods. Lint, package build, installed
UI smoke test, installer upgrade/restore (empty saved state), and all local
Markdown links / fenced Python and shell syntax checks also passed.

GitHub's isolated Ubuntu 24.04 runner also passed the installer and complete
privileged integration suite. Runtime constraints select a Python-3.10-compatible
platformdirs release on Ubuntu 22.04, with newer Python retaining its tested pin.

## Environment

Version 2.8.1: **10 web setup tests passed**, including real root systemd and
TLS proxy checks (2.273 seconds). Generated services use null standard input
without the newer `--foreground` option, so the same web service can also run
the older 2.3.0 CLI during rollback. Wheel and source distribution builds passed.

On 2026-10-19, an authorized Ubuntu 24.04 VPS was upgraded from 2.3.0 to 2.8.1.
The first interactive `splitforge web` wizard configured public IP HTTPS on
port 9090 and obtained a real Let's Encrypt IP certificate. An independent
Windows client verified the system-trusted certificate, its matching IP SAN
and an HTTP 200 session response without disabling TLS verification. Token
login, Secure session cookies, logout and the active renewal timer were checked.
An actual installation rollback then served version 2.3.0 through that same
HTTPS endpoint; restoring the recovery snapshot served 2.8.1 again. The final
web service, nginx and renewal timer were active. The host IPv4 main route
table matched its pre-upgrade snapshot and the SSH session remained connected.
This server had no registered profiles or applications: these deployment checks
do not establish live provider interoperability or customer workload continuity.

Version 2.8.0: **105 tests passed with root integration enabled** (145.593
seconds), plus the expanded desktop/mobile browser suite, lint and syntax checks.
The traffic integration transfers different-sized verified-TLS responses through
two root services in one actual tunnel namespace. The idle service receives none
of the other service's counters. It verifies app-only stopping, tunnel stopping,
native systemctl-restart blocking, reset/restart, persistent totals and unchanged
host routes. An additional six-test targeted run passed after adding a permitted
backup for a quota-blocked primary and unused monitor cleanup. Browser checks
cover seven traffic cards, fourteen RX/TX lines, quota draft retention, read-only
refusal and the Persian traffic page. Real rollback also confirms a post-snapshot
app's obsolete unit is removed rather than left enabled for the next boot.

Version 2.7.0: **99 tests passed with root integration enabled** (112.585
seconds), plus the browser suite, lint and documentation checks. Tests cover
encrypted round trips, unique ciphertext, tamper/wrong-password rejection,
private files, invalid references, authenticated HTTP downloads and explicit
restore confirmation. Real root systemd restoration covers stopped imports and
failed-start recovery. A separate real installed venv test changes its package
version and state, then verifies rollback restores both and its root workload.
Mocked failure tests cover restoration of the current version when old-version
activation fails. Browser checks cover password confirmation and demo refusal.

Version 2.6.0: the expanded real browser suite passed all seven Persian pages,
global and modal language switches, preserved dialog drafts, translated demo
errors, persisted preference after reload, reversible English navigation and
390px RTL overflow checks. A separate visible-label audit covered all pages and
app/profile/route forms. Raw journals/user names are intentionally excluded.

Version 2.5.1: targeted real Linux failover/probe tests (2 methods), authenticated
web unit checks (10 methods), and desktop/mobile browser checks passed. The real
probe confirms PID, network/mount namespace identity, isolated resolver and
fixture egress after failover; it rejects an intentionally mismatched saved
assignment and a stopped workload. Browser checks cover the button, demo guard
and historical result rendering. Version 2.5.0's full 90-test CI run also passed.

Version 2.5.0: **90 tests passed with root integration enabled** (88.028
seconds), plus the desktop/mobile browser suite, CI-policy lint, package build
and documentation checks. Real systemd tests verify the persistent monitor,
primary-to-backup process restart and namespace identity, verified backup egress,
both-down suspension with saved recovery intent, and unchanged host main routes.
Unit tests additionally cover startup failures, stale-probe/manual-stop races,
protected profile references and explicit Direct policy removal. Browser and
Textual checks exercise the primary/backup selector and Direct clearing it.

Version 2.4.2: **77 tests passed with root integration enabled**, plus the browser
suite, lint, build and documentation checks. Local HTTP download tests cover 503
retry, alternative source, actual streamed percentage/unknown-size progress,
truncated response retries, corrupt digest/size rejection, offline reuse and
cache-write failure. A separate real build used the pinned Go/source offline
artifacts to produce/install DNSTT into a temporary directory and execute its
help flags. The browser suite verifies the progress bar's 42% fixture value.

Version 2.4.1: **69 tests passed with root integration enabled** locally, plus
the desktop/mobile browser suite, lint, distribution build and documentation
checks. The diagnostics integration injects an unconditional namespace firewall
accept rule and a bad DNS file, detects both, rebuilds the tunnel, restores its
root workload in the same saved assignment, verifies fresh egress and compares
the host main route before/after. The authenticated HTTP integration also runs
the diagnostic action and receives structured results. Browser checks cover
scan/repair controls, confirmation, read-only demo refusal and finding rendering.

Version 2.4.0 setup checks include address/config injection rejection, separate
domain/IP ACME flags and certificate lineages, first interactive launch, private
saved settings, renewal scheduling, certificate failure rollback and failed public
readiness. Opt-in real Linux tests start/enable/restart an actual generated unit
and compare the host route table. A real isolated nginx process exercises the
generated TLS proxy with a specifically trusted fixture certificate, token login,
Secure cookies and rejected foreign Host/Origin headers. The fixture test does
not claim that a public CA issued a real domain/IP certificate. Public issuance
requires a reachable server and acceptance of the CA subscriber agreement.

Version 2.3.0: **54 Python tests passed with root integration enabled** locally,
including HTTP-driven profile management and a real root systemd workload
lifecycle. HTTP tests exercise token/session/logout/expiry, origin/host/CSRF
rejection, rate limiting, body limits, demo guard, secret filtering and serialized
job handling. Existing tunnel, failure, root reassignment and route checks pass.

The optional Playwright suite also passes in desktop Chrome (1440px) and a
390px mobile viewport. It checks dashboard data, route/app/profile forms, file
browsing, read-only refusal, auto core helpers, DNS edits surviving polling,
journal updates, Persian help, malicious-label escaping and logout. Actual
[desktop](assets/web-overview.png) and [mobile](assets/web-mobile.png) captures
were inspected. These are controlled tests, not an external web security audit.

To reproduce browser checks (Node 22+; development tools only):

```sh
npm install --no-save --package-lock=false playwright@1.62.1
npx playwright install chromium
splitforge web --demo
# In another terminal:
node tests/web_browser.cjs
```

CI installs Chromium's Linux dependencies and runs the same browser suite.
The web server must be running on loopback port 8765 for that check. Browser
tests use demo data; the opt-in Python HTTP integration exercises real systemd.

Version 2.1.0 adds focused tests for walkthrough navigation/language switching,
compact checklist cancellation, automatic dependency planning, demo no-install
behavior, installed-tool skipping and partial batch failure. These use the real
Textual interface with mocked installers, so they do not download packages.
The existing verified installer and network integration tests remain in CI.

- Windows workstation hosting Ubuntu 24.04 under WSL2, x86_64.
- systemd PID 1, Python 3.12.3, working network namespaces/nftables and `/dev/net/tun`.
- Xray v26.3.27; tun2socks v2.7.0; WireGuard tools 1.0.20210914;
  OpenVPN 2.6.19 installed.
- Textual 8.2.8, Rich 14.3.4, Typer 0.27.3, HTTPX 0.28.1, psutil 7.2.2,
  Pydantic 2.14.1. Exact runtime versions are in `requirements.lock`.
- Slipstream client v0.1.1 installed from verified release and CLI options checked.
- DNSTT client built and installed from pinned, SHA-256-verified source using a
  verified Go compiler. Source/compiler artifacts used the supported offline
  cache because of upstream access restrictions; modules retained checksum checks.

## Checks performed

| Check | Evidence / scope |
| --- | --- |
| State and imports | Atomic POSIX state persistence, references, URI parsing and forbidden config hooks |
| Root | One-off direct/tunneled execution, generated persistent root service, namespace inode assertions |
| Root service adoption validation | Implicit, explicit and numeric root; protected SSH/network aliases; root-wide user manager remains rejected |
| Namespace guards | Actual kernel namespace/nftables creation, default-deny policy, no direct default, IPv6 disabled |
| SOCKS5 | Real local Xray SOCKS server → namespace TUN/tun2socks → verified HTTPS/DoH |
| WireGuard | Real local encrypted peer handshake/data, client interface moved from root into its namespace |
| VLESS, VMess, Shadowsocks | Real local Xray transport servers; namespace TUN/tun2socks; verified DoH and HTTPS through each adapter |
| Trojan | Real TLS-enabled Xray server, explicitly trusted fixture CA, namespace DNS/HTTPS egress; certificate verification remains enabled |
| OpenVPN | Actual local TLS-authenticated client/server data path; root-created TUN moved into namespace; DNS/HTTPS and root service reassignment |
| Reassignment | Root service restarted from proxy → WireGuard → OpenVPN → Direct; PID and namespace identity checked |
| Failure | After proxy core stops, host-only listener remains reachable from root control but blocked from the workload namespace |
| Rollback | Simulated failed service startup restores previous unit content and saved assignment |
| Host routing | Host IPv4 main table compared before/after real integration scenarios; unchanged |
| Cleanup | Test-owned units/namespaces/veths/firewall/policy resources removed |
| UI | Six-page navigation, route modal and read-only demo; compact 80×24 mounting; actual exported screenshots inspected |
| Distribution | Real install into a separate /opt prefix, built wheel installation, public launcher and platform doctor |

The local HTTPS fixture uses a freshly generated test CA and matching server
certificate. The CA is explicitly trusted for those profiles; verification is
not disabled. Its synthetic response is `ip=192.0.2.80`, `loc=ZZ`. A real DoH
binary DNS response drives resolution through the profile. This proves that the
tested paths transport data, not that a public VPN provider advertises that IP.
Loopback VLESS/VMess tests exercise the base transport without TLS/REALITY.
The Trojan fixture adds its CA using Xray's documented
[`CertificateObject` with `usage=verify`](https://xtls.github.io/en/config/transports/tls.html).

## Run the routine suite

```sh
python3 -m venv .venv
.venv/bin/pip install -c requirements.lock -e .
.venv/bin/python -m unittest discover -s tests -v
```

The framework is stdlib unittest, with installed runtime dependencies for CLI/UI.
Root integration is skipped unless explicitly enabled. State locking tests need
POSIX; network operations are never performed merely by importing tests.

## Run actual kernel/systemd integration

Use an isolated Linux VM/lab with systemd and TUN. The test intentionally creates
real namespaces, interfaces, policy rules, nftables tables and root systemd
services; it cleans resources belonging to its random IDs. Do not run multiple
copies concurrently; some test subnets/slots are fixed.

```sh
sudo bash install.sh
sudo env SPLITFORGE_INTEGRATION=1 /opt/splitforge/venv/bin/python -m unittest discover -s tests -v
```

Install OpenSSL and WireGuard tools if using a custom environment. Xray and
tun2socks are required for proxy tests. The tests use controlled local servers,
without public VPN credentials, delegated DNS or external probe reachability.
CI runs the same opt-in suite on an isolated hosted Ubuntu runner.

## Remaining deployment validation

- Public-provider authentication, TLS/REALITY and each supported transport mode.
- OpenVPN provider-specific options/reconnect behavior, DNSTT/Slipstream
  delegated-domain interoperability; installed binary/help checks alone are not
  end-to-end tests of these protocols.
- UDP relay compatibility of individual proxy servers; DNS-tunnel adapters are TCP-only.
- Reboot with enabled real workloads, credential paths and provider readiness.
- Your host firewall manager, existing routing policy, kernel and VPS restrictions.
- Long-duration loss/recovery, MTU tuning, resource exhaustion and workload-specific
  crash/restart semantics. No throughput or availability SLA has been measured.
- Filesystem/process security of root workloads. Namespaces isolate the network,
  not all communication channels or malicious programs.

Before unattended deployment, rehearse these against the intended server and
keep a recovery console available. A passing route comparison verifies that
comparison; it cannot certify all SSH failure modes or unrelated network changes.
