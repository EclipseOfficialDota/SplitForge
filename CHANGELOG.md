# Changelog

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
