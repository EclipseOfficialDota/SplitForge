# ⚡ SplitForge

Per-application split tunneling for Linux VPS hosts.

**Development status: Part 1 — backend foundation.** The Textual interface,
public CLI, installer, and packaging are planned for subsequent parts.

## Included

- Validated profile imports for VLESS, VMess, Trojan, Shadowsocks, SOCKS5,
  WireGuard, and OpenVPN, plus DNSTT and Slipstream configuration.
- Network namespace creation, scoped host routing, namespace firewall guards,
  and a certificate-verified DNS-over-HTTPS stub.
- Systemd application execution, service assignment, and restart-based tunnel
  reassignment with rollback.
- Atomic JSON state storage and tunnel egress checks.

## Current limitations

- IPv4 only; shared profile namespaces require kill switches and DNS isolation.
- User bindings apply to future systemd user workloads. Existing processes
  require explicit restarts or individual service adoption.
- DNSTT and Slipstream need a SOCKS5 server behind the remote tunnel and carry
  TCP traffic only.
- Proxychains mode is a TCP convenience wrapper without namespace leak protection.
- Live Linux networking and systemd behavior have not been verified. The project
  is not yet certified for production use or a zero-SSH-interruption guarantee.

## Verification

Run the non-privileged checks from the repository root:

```sh
python -m unittest discover -s tests -v
```

Current Windows result: **9 passed, 1 Linux-only state test skipped**.
The networking command checks use mocks; they do not establish working VPN
connections or verify kernel firewall behavior.

## Layout

```text
splitforge/
├── state.py
├── core/
│   ├── netns.py
│   └── runner.py
└── protocols/
    └── manager.py
tests/
└── test_core.py
```

## License

MIT — see [LICENSE](LICENSE).
