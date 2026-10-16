# Security model and reporting

SplitForge is a privileged Linux networking application with a terminal UI and CLI.
There is no completed security audit or production/SSH-safety certification.

## Boundaries

- The control plane and protocol helpers run with root authority. Trust the
  machine administrator, installed Python code, systemd, kernel and upstream
  binaries. Keep their directories root-controlled.
- Managed workloads may use root or an ordinary account. Generated units remove
  capabilities and enable `NoNewPrivileges`; this does not turn a network
  namespace into a complete sandbox for hostile programs.
- Apps assigned to one profile share its namespace. They can share local network
  resources and aggregate counters; this is not per-app security separation.
- Namespace guards deny Direct fallback. Local Linux tests exercise DNS, IPv6
  disabling and blocked underlay access after core loss; see docs/VALIDATION.md. Proxychains mode does not provide that guard.
- Host control-plane DNS/transport is separate from application DNS. Local Unix
  sockets, host services, unrelated proxies, filesystem access and root compromise
  need additional controls outside this project's present scope.
- Existing root services are supported. SSH/network infrastructure and
  socket-activated services are rejected for adoption.
  User-manager binding is not live UID-wide routing or SSH-session migration.

## Configuration secrets

The default state file is `/etc/splitforge/state.json`. It can contain WireGuard
private keys, proxy passwords/UUIDs, inline OpenVPN keys and other sensitive
configuration. It is plaintext on disk with protected file permissions, not an
encrypted vault. Protect the containing directories and backups too.

Runtime files are under `/run/splitforge/PROFILE_ID/`. External OpenVPN credential
files can remain referenced by absolute path. Keep them available until profiles
are stopped and maintain suitable ownership/permissions. Do not commit private
profiles, `.env` files, state files, credentials or real subscription links.
`.gitignore` is a convenience and is not a secret-detection security control.

Use genuine TLS settings, matching DoH bootstrap addresses, and Slipstream server
certificate pinning. Do not fix connection errors by disabling certificate
verification or enabling arbitrary config hooks/plugins.

## Reporting

For ordinary defects, use [Issues](https://github.com/EclipseOfficialDota/SplitForge/issues)
with sanitized reproduction steps. Do not post credentials or a working exploit
that exposes private infrastructure publicly.

For a suspected security vulnerability, use GitHub's private vulnerability report
option **if the repository exposes it**. No private reporting email, response SLA,
bug bounty or audit program is currently declared. If private reporting is not
available, open a minimal public issue asking for a private channel without
including sensitive exploit details or secrets.

Only the current development source is maintained; there is no supported release
matrix yet. Preserve the source commit/version details in a report so the issue
can be reproduced without assuming a stable published release.
