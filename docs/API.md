# Python backend API reference

[Home](../README.md) · [Tutorial](GETTING_STARTED.md) · [Architecture](ARCHITECTURE.md)

These are the current Python APIs; CLI users should start with the tutorial. Network mutation requires Linux/root and working systemd.
Use the stable interpreter from the tutorial. All examples assume real profiles
and existing Linux accounts where named. Root workloads are supported.

## Initialize the main objects

```python
from splitforge.state import AppBinding, Profile, StateStore
from splitforge.core.netns import NetNS
from splitforge.core.runner import Runner
from splitforge.protocols.manager import ProtocolManager

store = StateStore()  # /etc/splitforge/state.json
manager = ProtocolManager(store)
runner = Runner(store, manager)
```

Do not print `store.snapshot()` or `Profile.config` into public logs: they may
contain private keys/passwords. A custom state path is supported for development,
but generated systemd units must retain access to it. The state path does not
relocate the backend's other `/etc`, `/run`, or systemd resources.

## Profile model

`Profile(name, protocol, config, ...)` is a dataclass.

| Field | Default / meaning |
| --- | --- |
| `name` | Required; unique saved profile name, 1–80 printable characters |
| `protocol` | Required; supported protocol identifier |
| `config` | Required dict; adapter-specific secret configuration |
| `id` | Random 8-character lowercase hexadecimal ID |
| `slot` | 0 before allocation; 1–4095 after save |
| `doh_url` | `https://cloudflare-dns.com/dns-query` |
| `doh_ip` | `1.1.1.1`; IPv4 bootstrap address |
| `exit_ip` | Last stored exit address, initially empty |
| `country` | Last stored two-letter country result, initially empty |
| `latency_ms` | Last stored HTTPS/DNS elapsed time or `None` |
| `probe_url` | Verified HTTPS trace endpoint; default Cloudflare `/cdn-cgi/trace` |
| `tls_ca_file` | Optional absolute custom CA bundle path; also applies to DoH |

Supported identifiers: `vless`, `vmess`, `trojan`, `shadowsocks`, `xray`,
`wireguard`, `openvpn`, `dnstt`, `slipstream`, `socks5`.

Computed properties: `namespace`, `interface`, `subnet`, `gateway`, `peer`.
Prefer validated import methods to constructing an adapter's internal `config`
dict manually. Names are labels; IDs determine resource names.

## AppBinding model

`AppBinding(name, argv=[], ...)` represents a command or an existing service.

| Field | Default / meaning |
| --- | --- |
| `name` | Required printable display label |
| `argv` | Argument list, with an absolute executable; required unless `service` is set |
| `id` | Random 8-character ID |
| `profile_id` | `None` for Direct, otherwise a saved profile ID |
| `user` | `nobody`; must exist; root is supported (CLI/UI default to root) |
| `cwd` | `/`; absolute working directory |
| `service` | Existing `.service` name or `None` |
| `kill_switch` | `True`; required true for a tunneled shared namespace |
| `isolate_dns` | `True`; required true for a tunneled shared namespace |
| `enabled` | `False`; saved management intent, not current process status |

Argument arrays do not implicitly run a shell. Use an explicit interpreter for
`.py`/`.sh` files. The runner does not automatically copy files, install app
dependencies, create users or fix permissions.

## StateStore

| Method | Result / side effect |
| --- | --- |
| `snapshot()` | Deep copy of validated state; empty v1 structure when file is absent |
| `profiles()` | List of `Profile` objects |
| `apps()` | List of `AppBinding` objects |
| `profile(name_or_id)` | Resolve exactly one name/ID; missing/ambiguous reference raises `KeyError` |
| `app(app_id)` | Resolve app by validated ID |
| `save_profile(profile)` | Allocate/preserve its slot and atomically persist; returns profile |
| `save_app(app)` | Validate assigned profile reference and persist; does not start a process |
| `delete_profile(profile_id)` | Delete unreferenced state entry; does not stop networking/remove unit |
| `delete_app(app_id)` | Delete state entry only; prefer `Runner.remove()` for a managed app |
| `assign_user(user, profile_id)` | Save mapping; `None` removes it; use runner for systemd behavior |
| `operation(scope='state')` | Linux flock context for mutation coordination |

The store enforces unique profile names and subnet slots, validates schema and
stored app/user references, and writes mode-0600 files. It does not encrypt
configuration. Preserve root-controlled parent directories. Direct store
deletion is not lifecycle teardown.

## ProtocolManager

### imports and dependencies

```python
manager.import_profile(source, name=None, replace_id=None)
manager.dns_tunnel(
    name, protocol, domain, resolver, public_key='', certificate='', replace_id=None
)
manager.dependencies(protocol)
manager.missing(protocol)
```

`name` is keyword-only for `import_profile`; `public_key`/`certificate` are
keyword-only for `dns_tunnel`. Import accepts a supported URI or an existing
`.conf`, `.ovpn`, `.json` path and returns a saved `Profile`. `dns_tunnel`
constructs/saves DNSTT or Slipstream configuration; neither method starts it.
Both support keyword-only `replace_id` for a stopped profile. Replacement
retains ID/slot, assignments, DNS and probe settings, clearing old metrics.
DNS-tunnel edits can preserve an existing key/certificate when omitted.
See [Protocols](PROTOCOLS.md) for exact forms/restrictions.

`dependencies()` returns executable names; `missing()` filters by executable
discovery. They do not install anything or validate versions/kernel support.

### lifecycle

```python
manager.start(name_or_id)
manager.stop(name_or_id)
manager.remove(name_or_id)
manager.test(name_or_id, persist=True)
manager.status(name_or_id)
```

- `start()` checks tools, writes the persistent profile unit, starts it and
  enables it for boot. The internal up helper creates networking and tests egress.
- `stop()` stops/disables that profile unit; dependent apps can stop as well.
  It retains saved profile and app assignments.
- `remove()` requires no app/user references, stops/removes its owned unit and
  networking, then deletes the profile. CLI, TUI and web share this guard.
- `test()` requires an existing namespace, performs a namespace HTTPS probe,
  returns `exit_ip`, `country`, `latency_ms`, `measurement`; it persists the first
  three by default. `persist` is keyword-only. No host HTTP fallback is used.
- `status()` returns `id`, `name`, `active`, `namespace`, `exit_ip`, `latency_ms`,
  and `bandwidth` with `rx`/`tx`. It does not make a fresh live egress check.

`latency_ms` is elapsed HTTPS/DNS time including retries. Bandwidth is aggregate
interface bytes since the current interface lifecycle, not per-app totals.

Internal `_up`, `_down`, `_proxy`, `_service` and listener helpers are not public
entry points. Use `start`/`stop` so systemd lifetime and boot state stay aligned.

## Runner

### persistent applications and existing services

```python
runner.bind(app_id, profile_name_or_id, start=True)
runner.stop(app_id)
runner.remove(app_id)
runner.running(app)
runner.unit(app)
```

`start` is keyword-only. `bind` returns the updated binding. The app must first
exist in state. Passing `None` assigns Direct. The operation restarts the app
when `start=True`; changing a profile is not transparent process migration.

`stop` stops the unit, disables generated app units and records `enabled=False`.
`remove` stops it, removes only its owned unit/drop-in, reloads systemd and
deletes the app record. It does not restart an adopted service's original unit.
`running` queries `systemctl is-active`; `unit` computes the managed or adopted
service name.

### one-off commands

```python
exit_code = runner.execute(
    ['/usr/bin/python3', '/srv/app/task.py'],
    profile_name='wg-lab', user='app-user', cwd='/srv/app'
)
```

Options after `argv` are keyword-only. `execute` returns the `systemd-run`
wrapper's exit status. It resolves the executable, starts the selected profile
if needed and uses a transient service. It does not create an app registration.
When `profile_name` is absent, saved user mapping is consulted; without a mapping
execution uses Direct. There is no separate bypass-mapping sentinel here.

### user managers

```python
unit = runner.bind_user('labuser', 'wg-lab')
runner.bind_user('labuser', None)
```

Requires UID >= 1000 and non-root. It writes/removes the owned `user@UID.service`
drop-in and saves the mapping; it does not restart the manager. Existing sessions
and same-UID processes outside the user manager do not migrate.

### TCP wrapper

```python
exit_code = runner.proxychains(
    'vless-lab', ['/usr/bin/curl', 'https://example.com'], user='app-user'
)
```

Requires `proxychains4` and a proxy profile; WireGuard/OpenVPN are rejected.
It supplies a scoped SOCKS configuration using a systemd credential mount.
This is an LD_PRELOAD-style TCP convenience mode, not isolated networking.
Static binaries, nonintercepted calls, application UDP and DNS behavior must not
be assumed protected. Prefer `execute()` for the namespace workflow.

## Profile speed and volume limits

Use `splitforge.core.speed.set_limits(store, profile_id, download_bps, upload_bps)`
for live/persistent shared profile caps (integer bits/second; zero disables that
direction). `TrafficStore(store).set_quota('profiles', profile_id, byte_limit)`
sets its separate volume budget; `None` disables the budget. Mutations require
Linux root. New/stopped profiles can be configured before startup.

The authenticated, CSRF-protected web job endpoint accepts `traffic.speed` with
`id`, integer `download` and `upload`, and `traffic.quota` with `kind='profiles'`,
`id`, `limit` (bytes or null), `warning` (1–99) and optional boolean `reset`.
Both speed fields must be explicit, including zero when disabling a direction.
See [Traffic](TRAFFIC.md) for enforcement scope and short-burst/volume overshoot
limits. Host-side proxychains execution rejects limited profiles.

## Aggregation profiles

`manager.bond(name, member_ids, relay_host, relay_port, token)` saves an aggregate
profile after validating member references and ensuring they have no TUN-based
budgets that their proxy transport would bypass. Member profiles must be
independent TCP proxies; nested groups and WireGuard/OpenVPN members are rejected.
Use ordinary `manager.start`, app binding and removal for the output. Removing
a referenced member is rejected before stopping its services.

The web job `profile.bond` accepts `name`, `members` (2–8 distinct IDs),
`relay_host`, integer `relay_port`, and a private 64-hex `token`. Session/CSRF and
serialized-job protection apply. State snapshots expose path counts, not tokens.
`dns_tunnel` additionally accepts `protocol='noizdns'` and optional `username`
and `password` for the remote SOCKS backend. See [Bonding](BONDING.md) for the
destination installation and reliability/throughput limits.

## NetNS and low-level helpers

`NetNS` exposes `exists`, `create`, `command`, `guard`, `activate`, `destroy`
and `bandwidth`. These are low-level primitives; the manager normally owns their
order. Manually destroying a namespace while units are running can leave live
processes holding it or inconsistent state. `command()` is a privileged raw
namespace command facility, not an unprivileged app runner.

`run()` executes an argument array without a shell and captures output. Checked
nonzero exits raise a sanitized `RuntimeError`; inspect relevant journals for
details. `unit_word()` escapes generated systemd arguments. `atomic_secret()`
writes owned configuration atomically. These helpers are implementation details
rather than a general administration framework.

## Errors and ownership rules

Expected failures include `ValueError` for invalid/rejected config, `KeyError`
for missing references, `PermissionError` for non-Linux/non-root mutations,
`FileNotFoundError` for absent files/executables, `KeyError` for absent account
lookups, and `RuntimeError` or
timeouts for external command/health failures. Exact exception text can change.
The command wrapper intentionally avoids echoing full secret-bearing arguments.

Keep state while units still reference it. Stop/unbind workloads and user
managers, stop profiles, remove specific persistent unit files, then delete
unreferenced state if desired. The [tutorial cleanup](GETTING_STARTED.md#logs-stop-and-remove)
shows this order.
