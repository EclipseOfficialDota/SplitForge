# Validation record and reproducible checks

[README](../README.md) · [Setup](GETTING_STARTED.md) · [Architecture](ARCHITECTURE.md)

Recorded during development on 2026-10-16/17. These are actual local results,
not an external audit, performance benchmark or universal production certificate.
GitHub CI has its own independently visible run status.

Final local suite: **31 tests passed, zero skipped**, with
`SPLITFORGE_INTEGRATION=1` (22.858 seconds). The same suite without opt-in
skips the three privileged integration methods. Lint, package build, installed
UI smoke test, installer upgrade/restore (empty saved state), and all local
Markdown links / fenced Python and shell syntax checks also passed.

GitHub's isolated Ubuntu 24.04 runner also passed the installer and complete
privileged integration suite. Runtime constraints select a Python-3.10-compatible
platformdirs release on Ubuntu 22.04, with newer Python retaining its tested pin.

## Environment

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
