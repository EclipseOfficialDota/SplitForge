# Changelog

## 2.3.0 — 2026-10-17

- macOS Terminal-style browser dashboard with responsive layout, app routing,
  profile imports/lifecycle/replacement, server file picker, encrypted DNS,
  core checklist, live journal and English/Persian quick-start guide.
- `splitforge web` with loopback binding, private access token, expiring sessions,
  CSRF/Host/Origin protection, sign-in rate limit and no-cache/framing headers.
- Serialized background operations and readable progress/failure results; read-only
  demo mode supports browser previews without root or server mutation.
- Real HTTP/systemd root workload test, authentication/API security tests,
  Playwright desktop/mobile checks and packaged local web assets.

## 2.2.0 — 2026-10-17

- `splitforge update` fetches the official master revision without requiring an
  existing checkout, detects custom install prefixes and preserves custom state.
- Private state backup before installation; restore of saved enabled workloads;
  concurrent-update lock and same-revision skip (`--force` to reinstall).
- Optional protocol cores are retained during self-update. The installer now
  includes git and records its installed revision for future no-op detection.
- Failure/backup/locking/CLI tests and bilingual self-update instructions.

## 2.1.0 — 2026-10-17

- In-app six-step walkthrough with English/Persian language switching, accessible
  from the sidebar or F1 without modifying configuration.
- Core checklist (F2 / Logs & Tools) with installed/missing detection, recommended
  selections and automatic required proxy helpers.
- Sequential installation through the existing verified installer, visible batch
  progress, installed-tool skipping and per-core failure reporting without
  discarding successful installations. No profiles start during installation.
- Read-only demo support and compact-terminal modal tests.

## 2.0.0 — 2026-10-17

- Complete six-page Textual terminal interface with dashboard, app/profile
  routing, modal selection, file/process/service pickers, DNS controls and logs.
- Public Typer CLI and Ubuntu/Debian installer with isolated Python environment,
  constrained runtime dependencies and verified upstream binary downloads.
- Root command and service support, including services with implicit/numeric
  root identity; SSH/network infrastructure adoption remains protected.
- Stopped-profile configuration replacement preserves IDs and assignments.
- Configurable verified HTTPS probes and private CA bundles for isolated networks.
- Correct tun2socks flags and resolver/NSS bind properties verified against
  installed upstream versions and real systemd units.
- Actual local Linux coverage for SOCKS5, WireGuard, OpenVPN, VLESS, VMess,
  Shadowsocks, TLS Trojan, root reassignment and fail-closed underlay access.
- CI checks/builds, package resources, real demo screenshots and bilingual
  operator documentation. See [validation limits](docs/VALIDATION.md).
