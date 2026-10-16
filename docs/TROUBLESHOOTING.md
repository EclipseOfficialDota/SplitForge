# Troubleshooting and recovery

[Home](../README.md) · [Tutorial](GETTING_STARTED.md) · [Architecture](ARCHITECTURE.md)

Use these diagnostics on the Linux lab host. They are instructions, not recorded
integration results. Do not publish raw state, full profile URIs, WireGuard
configuration, passwords or certificate private keys with a bug report.

## Identify the failure layer

| Symptom / message | Likely layer | First action |
| --- | --- | --- |
| `splitforge: command not found` | Installation/PATH | Run install.sh; inspect /usr/local/bin/splitforge and its venv target |
| `install.sh` / `pyproject.toml` missing | Later distribution part | Follow manual lab setup, not `pip install .` |
| `No module named splitforge` in a service | Package unavailable to helper interpreter | Verify stable venv import from `/tmp` |
| `No module named pwd` | Non-Linux runner import | Use Linux for networking/runner |
| Linux/root permission error | Privileged operation outside target environment | Use intended Linux sudo interpreter |
| `Missing dependencies: ...` | Executable discovery | Install selected upstream/distribution tool in system PATH |
| `Profile name already exists` | Duplicate import | Reuse saved ID/name instead of importing again |
| Profile/app not found | Wrong state path, name or ID | List IDs from the same `StateStore` |
| `Subnet ... conflicts` | Host/container routes overlap address pool | Inspect route ownership; do not delete unrelated routes |
| Policy slot or resource already occupied | Routing/name conflict or prior incomplete teardown | Inspect the exact ID/slot and owned resources |
| WireGuard directive rejected | wg-quick hook/unsupported field | Use supported no-hook client configuration |
| OpenVPN directive rejected | Strict client allow-list | Review provider options in Protocols guide |
| Proxy listener unavailable/owned by another process | Core startup, CLI mismatch or port conflict | Check the expected core/transport journal |
| Tunnel interface never ready | OpenVPN auth/handshake/hook/topology | Inspect profile and OpenVPN core journals |
| Egress/DNS probe failed | Upstream, DNS, TLS or service environment | Inspect DNS/tun/core together |
| Registered user must match service | App/service account | Match effective User=; absent User= or User=0 means root |
| Socket-activated service rejected | Existing service activation path | Use a dedicated ordinary service |
| Shared guard settings rejected | Per-app weakening in shared namespace | Keep both guard flags true for tunneled apps |
| Assignment rollback failed | Old service could not be restored | Inspect service state; keep it stopped until repaired |

## 1. Find the real IDs

Use the stable interpreter from the tutorial:

```sh
sudo /opt/splitforge/venv/bin/python - <<'PY'
from splitforge.state import StateStore

store = StateStore()
for profile in store.profiles():
    print(profile.id, profile.name, profile.protocol,
          profile.namespace, 20000 + profile.slot, 12000 + profile.slot)
for app in store.apps():
    print(app.id, app.name, app.profile_id, app.enabled)
PY
```

Names may differ from examples. Use actual generated IDs. In the following
shell examples, replace `0123abcd` and `89abcdef` with your profile/app IDs:

```sh
SF_PROFILE_ID=0123abcd
SF_APP_ID=89abcdef
```

## 2. Inspect systemd and the journal

```sh
sudo systemctl status "splitforge-profile-${SF_PROFILE_ID}.service" --no-pager
sudo journalctl -u "splitforge-profile-${SF_PROFILE_ID}.service" -b --no-pager -n 100
sudo journalctl -u "splitforge-core-${SF_PROFILE_ID}.service" -b --no-pager -n 100
sudo journalctl -u "splitforge-tun-${SF_PROFILE_ID}.service" -b --no-pager -n 100
sudo journalctl -u "splitforge-dns-${SF_PROFILE_ID}.service" -b --no-pager -n 100
sudo journalctl -u "splitforge-transport-${SF_PROFILE_ID}.service" -b --no-pager -n 100
sudo journalctl -u "splitforge-app-${SF_APP_ID}.service" -b --no-pager -n 100
```

Only relevant adapter roles exist. Transient units can disappear after exit
because they use collection, while their journal records may remain. For an
adopted service, inspect its original unit name rather than `splitforge-app-ID`.

The backend command wrapper intentionally emits sanitized command errors.
Service journals provide the next layer of detail. Redact metadata/secrets
before sharing excerpts. Do not automatically attach `/etc/splitforge/state.json`.

## 3. Check namespace, interface and guard state

Read-only inspection:

```sh
sudo ip netns list
sudo ip -n "ns-${SF_PROFILE_ID}" link show
sudo ip -n "ns-${SF_PROFILE_ID}" -4 address show
sudo ip -n "ns-${SF_PROFILE_ID}" -4 route show
sudo ip netns exec "ns-${SF_PROFILE_ID}" nft list table inet splitforge
sudo nft list table inet "sf_${SF_PROFILE_ID}"
ip -4 route show table main
ip -4 rule show
```

The namespace should have the adapter's tunnel default route and the guard
table. The host veth is not a general forwarding escape. Existing host nftables
chains may still reject proxy traffic even when SplitForge's own narrow rule
accepts it; nftables accept in one base chain does not override every later chain.
Inspect ownership before changing existing firewall policy.

The profile oneshot can remain `active` while a core is failed. `active=True`,
an existing TUN interface, or an old exit IP alone does not prove connectivity.
Use `manager.test()` for a fresh end-to-end check.

## 4. DNS, HTTPS and exit-IP issues

Check the DNS helper first. Defaults use `cloudflare-dns.com` with bootstrap
IPv4 `1.1.1.1`. A blocked upstream, invalid system clock, missing CA certificates,
wrong bootstrap IP, or endpoint incompatible with HTTPS DNS can cause failures.
Do not resolve TLS errors by disabling verification.

In your initialized API context, test name resolution using the same managed
namespace properties as real apps:

```python
runner.execute(
    ['/usr/bin/getent', 'ahostsv4', 'example.com'],
    profile_name='wg-lab', user='splitforge-demo', cwd='/tmp'
)
print(manager.test('wg-lab'))
```

The managed runner applies resolver/NSS mounts and selected host resolver IPC
masks. A hand-written root `ip netns exec` application command is not a complete
substitute for that service environment when diagnosing DNS isolation.

The Cloudflare trace probe is a specific external dependency. Endpoint filtering
or blocking can fail startup even if some other tunnel destinations work.
Its elapsed measurement is not an ICMP ping. `country` is the trace response's
location code, not a separately maintained local GeoIP database.

If the visible exit matches the host address, inspect the actual upstream path
and chosen profile. Do not assume a profile label or successful import proves
the remote server exits somewhere different from the host.

## 5. WireGuard-specific checks

The interface lives inside the namespace, so host `wg show` alone may not list it:

```sh
sudo ip netns exec "ns-${SF_PROFILE_ID}" wg show "wg-${SF_PROFILE_ID}" latest-handshakes
```

Review endpoint reachability, server peer configuration, keys, allowed IPs and
host-side firewall. Interface creation does not establish a handshake. Do not
publish `wg showconf` or dump output containing private keys. Provider container
restrictions can prevent kernel interface creation even when `wg` is installed.

## 6. OpenVPN and DNS-tunnel checks

OpenVPN must authenticate noninteractively. External files normalized during
import must remain available, including after reboot. Inspect version/topology
and the controlled up-hook error if the namespace interface never becomes ready.
Do not globally start the provider's `.ovpn` file to work around the adapter.

For DNSTT/Slipstream, a local listening TCP port proves only local startup.
The remote forwarding target must really be a SOCKS5 service. A remote HTTP
proxy, SSH port, or arbitrary TCP target is not equivalent. Confirm your delegated
domain/server setup, keys/certificate and the installed client's documented flags.
Application UDP is intentionally blocked on these adapters.

## 7. App permissions and service restrictions

Check the `User=`, interpreter, working directory and file traversal permissions.
The runner does not install app dependencies or provide the interactive shell's
environment. Use explicit interpreter/configuration paths. A process under
`/root` is typically not readable by the non-root workload account.

Generated units remove capabilities and prohibit gaining privileges. Applications
requiring raw sockets or privileged setup may need an appropriately redesigned
service rather than weakening namespace protections. App startup success and
long-term app health are separate from profile health.

## 8. Reassignment or teardown failure

Keep state and external credential files while recovering; helpers need them to
identify the profile. Stop/recover affected workloads before changing networking.
Use `Runner.stop`/`remove` and `ProtocolManager.stop` before manually deleting a
specific owned unit. The [cleanup sequence](GETTING_STARTED.md#logs-stop-and-remove)
avoids leaving boot units pointing at missing state.

If a namespace/resource remains, compare the actual ID, interface alias/name,
route table, rule and services before removing anything. Other processes may
hold namespace references. Do not use `nft flush ruleset`, `ip route flush table
main`, blanket SSH restarts or broad wildcard deletion as a cleanup shortcut.

## 9. Testing host-route preservation and failure behavior

On an isolated lab host, record `ip -4 route show table main` before and after
profile startup/stop and compare the results. Also track the added dedicated
table/rule and verify removal. Account for unrelated DHCP/host networking changes.
A route comparison does not independently prove SSH or DNS safety.

Before claiming production readiness, deliberately test tunnel/core loss,
packet drops, DNS failure, invalid config, rollback failure and reboot. Observe
the managed application's actual traffic and verify that it never falls back
to host egress while configured for an isolated profile. Local namespace,
core-loss, DNS, WireGuard and root reassignment results are recorded in
[Validation](VALIDATION.md). Public-provider, reboot and failure combinations
beyond that record remain deployment-specific checks.

## Useful bug reports

Include the source commit, distro, Python/systemd/kernel versions, adapter core
versions, which API call failed, sanitized exception/journal excerpts, and
whether cleanup/reboot was involved. State what you observed and what you
expected. Avoid raw secrets, exact private infrastructure details and private
configuration attachments. See [Contributing](../CONTRIBUTING.md).
