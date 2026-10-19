# Changelog

## 2.9.0 — 2026-10-19

- Shared per-profile upload shaping and download policing, live changes and
  persistent caps restored before managed workloads start. Separate Mbps controls
  in profile/traffic cards and `traffic speed` CLI with explicit decimal kbit/s.
- Volume budgets can be saved for stopped/new profiles. Profile cards expose
  budget controls alongside speed settings; English/Persian labels and help.
- Failed speed changes restore prior rules; failed recovery disables the tunnel
  interface. Limited profiles reject new host-side proxychains launches, which
  bypass namespace interface accounting. Existing such workloads must be stopped
  and relaunched using namespace execution.
- Real isolated TCP transfers verify both directions, policy persistence,
  live rollback/removal, failed-recovery shutdown and unchanged host main routes.

## 2.8.1 — 2026-10-19

- Generated web units explicitly use null stdin and avoid the newer foreground
  flag, preserving listener compatibility when rolling back to web-capable 2.3.

## 2.8.0 — 2026-10-19

- Independent per-service kernel IP counters, persistent tunnel/interface totals,
  rate graphs, manual usage periods, warning thresholds and sampled stop budgets.
  Native startup conditions enforce saved app/tunnel budgets across restarts;
  missing accounting on a limited workload fails closed. No estimated allocation
  of shared tunnel traffic to applications.
- English/Persian traffic page, quota dialogs and CLI controls. Counter history,
  quotas and usage periods are included in encrypted backups and version rollback.
- Rollback removes obsolete owned units before restoring the selected state,
  including apps added after the snapshot, and reapplies future user bindings.
- Real integration covers two root apps sharing one namespace, independent
  measurements, per-app/per-tunnel stops, reset/restart, quota-blocked primary
  startup through a permitted backup, and monitor cleanup.

## 2.7.0 — 2026-10-19

- Password-encrypted, authenticated AES-256-GCM/Scrypt profile/settings backups,
  public trust-anchor portability and private pre-restore recovery. Web export
  downloads require authentication; web restores retain access and keep imported
  workloads stopped. CLI can explicitly restart trusted commands/redeploy web.
- Pre-update snapshots now retain the complete previous Python environment,
  matching state and web configuration. `rollback --list` / `rollback --backup ID`
  restore the environment and state together; failed activation recovers current
  installation and state. Matching active web services restart after maintenance.
- Restore handles automatic backup policies without requiring a failed primary
  to start first. Stop/remove also validates protected adopted services.

## 2.6.0 — 2026-10-19

- Global English/Persian switch on the login page, panel and open dialogs;
  persistent browser preference, RTL layout, translated pages/forms/accessibility
  labels, status/progress, diagnostic findings/remedies and error guidance.
- Language changes retain in-progress form data and routes. Technical commands,
  user-defined names and raw journals remain original; operation details are
  separately expandable beneath translated summaries.
- Browser regression covers all seven Persian pages, errors, language persistence,
  open-dialog drafts, bidirectional switching and a 390px RTL viewport.

## 2.5.1 — 2026-10-19

- App Router's **Test route** and `splitforge app test NAME` check HTTPS egress,
  resolved addresses and DNS configuration in the running main process's pinned
  network **and mount** namespaces, with its UID and capabilities removed.
- Reject stopped/restarted workloads, mismatched assignments and unsupported
  chroot services; never substitute a profile-only or host probe. Results show
  their PID, route and measurement time and are retained only in panel memory.

## 2.5.0 — 2026-10-19

- Per-application primary/backup tunnel policy in App Router and `bind --backup`.
  A separate permanent systemd monitor checks namespace guards/DNS/routes and
  real egress, switches after two failures, and restarts inside the backup.
- Both tunnels down leaves the workload stopped with its saved intent retained;
  Direct is never selected automatically. Healthy backups remain selected to
  avoid flapping; reapply the primary explicitly when desired.
- Concurrent manual stops/reassignments supersede stale health probes. Backup
  references protect profiles from deletion. Upgrade stop/restore and diagnostics
  preserve policy and quiesce the monitor during maintenance.

## 2.4.2 — 2026-10-18

- Late refresh/journal callbacks tolerate dashboard shutdown; a real shutdown
  regression check prevents the intermittent Textual worker crash seen in CI.

- Bounded streaming downloads with three attempts for transient failures,
  alternate official Go/GitHub sources and accurate byte/percentage progress.
- Automatic private SHA-256-keyed artifact cache, existing offline cache support,
  no unverified cache writes and hard failure on checksum/size violations.
- Web progress bars and terminal/CLI progress reports, including indeterminate
  source-build/unknown-length phases. Successful verified downloads remain usable
  when the optional cache is unavailable.

## 2.4.1 — 2026-10-18

- Health checks and explicit repair in Live logs: required cores, systemd/TUN,
  tunnel lifecycle, namespace routes/guards/DNS, egress, workloads and web ports.
- Structured findings, suggested fixes, repaired-state badges and asynchronous
  progress. Repair reinstates owned namespaces and enabled workloads using their
  saved tunnel assignments; Direct is never selected as a repair fallback.
- Real injected firewall/DNS damage test verifies root workload recovery and
  unchanged host routes. Provider firewall visibility remains explicitly limited.

## 2.4.0 — 2026-10-18

- First interactive `splitforge web` launch opens a setup wizard before serving.
  `splitforge web setup` offers permanent local access, public HTTP or automatic
  trusted HTTPS for a domain or public IP, with selectable ports.
- Isolated Certbot 5.4+ installation, webroot ACME validation, short-lived IP
  certificates and twice-daily automatic renewal with nginx reload.
- Public nginx Host/Origin checks and secure HTTPS cookies retain token/session
  protection. Backend remains on loopback. Setup checks actual readiness and
  restores prior owned files/services on certificate or startup failure.
- Real Linux tests cover permanent service startup/restart, host-route
  preservation and generated nginx TLS login/session/Host/Origin behavior.

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
