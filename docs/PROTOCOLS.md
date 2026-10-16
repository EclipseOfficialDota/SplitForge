# Protocol imports and upstream requirements

[Home](../README.md) · [Tutorial](GETTING_STARTED.md) · [API](API.md)

This describes implemented adapters, not verified interoperability. A parsed
profile can still fail configuration validation, authentication or reachability.
Use the privileged stable Python environment from the tutorial.

## Shared setup

```python
from pathlib import Path
from splitforge.state import StateStore
from splitforge.protocols.manager import ProtocolManager

store = StateStore()
manager = ProtocolManager(store)
```

Names must be unique. Import creates a new ID, not an in-place update. Stop an
active profile before changing saved configuration; starting an already active
unit does not force a reload. File imports are limited to 2 MB.

## Xray family

Read private URIs from a protected file rather than putting them in shell history:

```python
uri = Path('/root/splitforge-profiles/vless.uri').read_text().strip()
profile = manager.import_profile(uri, name='vless-lab')
print(profile.id)
```

| Family | Accepted form / behavior |
| --- | --- |
| VLESS | `vless://UUID@host:port?...`; UUID, optional flow, encryption set to `none` |
| VMess | `vmess://BASE64_JSON`; common `add`, `port`, `id`, `aid`, `net`, `tls` fields |
| Trojan | `trojan://PASSWORD@host:port?...`; TLS defaults on |
| Shadowsocks | `ss://BASE64_CREDENTIALS@host:port`; legacy whole-authority base64 also parsed |
| SOCKS5 | `socks5://host:port` / `socks://host:port`; optional URL-encoded credentials |

These are syntax forms, not real credentials. URL-encode special characters.
The URI parser accepts `tcp`, `raw`, `ws`, `grpc`, `httpupgrade` and `xhttp`
transport names, with common `path`, `host`, `serviceName`, `mode`, `sni`, `fp`
and `alpn` parameters. Security accepts `none`, `tls` or `reality`. REALITY
requires `pbk` and `sni`; `sid`/`spx` are mapped when supplied.

Unsupported transport names and SIP003 `plugin` URIs are rejected. Other URI
extensions are not a compatibility promise. TLS verification is not disabled by
an insecure URI flag. For advanced settings, use a compatible native outbound.

### Native Xray JSON

```python
profile = manager.import_profile(
    '/root/splitforge-profiles/outbound.json', name='json-lab'
)
```

The file must be one outbound object or a document whose `outbounds` array
contains exactly one `vless`, `vmess`, `trojan`, `shadowsocks` or `socks` outbound.
Multi-outbound input, `freedom`, and custom top-level `routing`/`reverse` settings
are rejected. Supplied top-level inbounds are not used. This is not a full Xray
configuration merger; SplitForge supplies its own scoped SOCKS inbound.

Startup runs `xray run -test -config ...`. The installed Xray must accept the
generated schema and your outbound. UDP depends on protocol/server compatibility;
an upstream SOCKS5 service must provide an actual UDP relay for UDP to work.

## WireGuard

```python
profile = manager.import_profile(
    '/root/splitforge-profiles/client.conf', name='wg-lab'
)
```

- Needs at least one IPv4 `Address` and a peer covering `0.0.0.0/0`.
- Mixed IPv6 addresses are not assigned; an IPv6-only profile is rejected.
- MTU defaults to 1420 and must be within 576–9000.
- `DNS` is ignored; application DNS belongs to the namespace DoH stub.
- `PreUp`, `PostUp`, `PreDown`, `PostDown`, `SaveConfig` and `Table` are rejected.
- Only recognized interface/peer fields reach `wg setconf`.

Do not substitute host `wg-quick up`. The interface is created/configured on
the host, moved into the profile namespace, and assigned addresses/default route
there. Its encrypted UDP socket retains the host birthplace namespace.

Upstream: [WireGuard namespace integration](https://www.wireguard.com/netns/).

## OpenVPN

```python
profile = manager.import_profile(
    '/root/splitforge-profiles/client.ovpn', name='ovpn-lab'
)
```

This adapter supports a restricted client configuration:

- TUN only; SplitForge supplies the interface name/type.
- Recognized client/network/crypto options and supported inline blocks.
- Arbitrary scripts, plugins, includes, alternative `iproute`, daemonization,
  and options outside `OVPN_ALLOWED` are rejected.
- Imported routes, redirects, pushed-DNS directives and custom `pull-filter`
  statements are removed; the namespace engine owns routes/DNS.
- External credential paths become absolute relative to the original file.
  Those referenced files must remain available and root-readable.
- Noninteractive authentication needs an explicit credential file or supported
  inline data. There is no password-prompt UI.

The root-side process keeps its transport socket on the host. Automatic route
and address manipulation is disabled; a controlled up-hook moves/configures
TUN inside the namespace. Persistent TUN/key handling is requested, and DCO is
disabled when detected OpenVPN is 2.6+. The core has no unconditional systemd
restart policy; inspect failures and explicitly restart the profile.

Review incompatible provider options rather than weakening the allow-list to
silence an error. The exact list is `OVPN_ALLOWED` in
[manager.py](../splitforge/protocols/manager.py).
Upstream: [OpenVPN manual](https://openvpn.net/community-docs/community-articles/openvpn-2-6-manual.html).

## DNSTT

DNSTT forwards TCP; it is not itself a SOCKS server. Provision DNS delegation,
the remote server/keys, and a SOCKS5 service behind its remote TCP endpoint
separately. This adapter expects to speak SOCKS5 through that forwarding path.

```python
public_key = Path('/root/splitforge-profiles/dnstt.pub').read_text().strip()
profile = manager.dns_tunnel(
    name='dnstt-lab', protocol='dnstt',
    domain='tunnel.example.com',
    resolver='https://cloudflare-dns.com/dns-query',
    public_key=public_key,
)
```

Replace the example domain with your real delegated domain. The key must have
64 hexadecimal characters. Resolver prefixes map to core arguments:

| Resolver form | DNSTT option |
| --- | --- |
| `https://...` | `-doh` |
| `tls://HOST:PORT` | `-dot` |
| `udp://HOST:PORT` | `-udp` |

The namespace rejects non-loopback UDP for this adapter. Local DNS UDP/TCP is
still accepted by the stub and forwarded as HTTPS over TCP. UDP-dependent apps
need another profile type. Upstream:
[DNSTT proxy examples](https://github.com/Mygod/dnstt).

## Slipstream

This targets the Mygod/slipstream-rust `slipstream-client` CLI. It requires a
remote SOCKS5 service behind the tunnel, a real domain/server, an IPv4 resolver
endpoint, and a PEM server certificate for pinning.

```python
profile = manager.dns_tunnel(
    name='slip-lab', protocol='slipstream',
    domain='tunnel.example.com', resolver='1.1.1.1:53',
    certificate='/root/splitforge-profiles/slipstream-server.pem',
)
```

Replace domain/resolver values for your deployment. The certificate contents
are copied into state and the private runtime directory. IPv6 resolver addresses
and an unpinned configuration are not accepted here. This adapter carries TCP;
general application UDP is blocked. Other similarly named Slipstream projects
may expose different flags and cannot be assumed interchangeable.

Upstream: [Slipstream Rust usage](https://github.com/Mygod/slipstream-rust/blob/main/docs/usage.md).

## Encrypted application DNS

Namespace applications use UDP/TCP `127.0.0.53:53`. The stub opens verified HTTPS
to a bootstrap IPv4 address through the tunnel. Defaults:

| Profile field | Default |
| --- | --- |
| `doh_url` | `https://cloudflare-dns.com/dns-query` |
| `doh_ip` | `1.1.1.1` |

For an inactive profile:

```python
profile = store.profile('wg-lab')
profile.doh_url = 'https://cloudflare-dns.com/dns-query'
profile.doh_ip = '1.1.1.1'
store.save_profile(profile)
```

Change URL/IP coherently: the bootstrap server must present a valid certificate
for the URL hostname. It avoids circularly resolving the DoH host before DNS
works. Saving settings does not reload a running helper.

The DNS carrier resolver used by DNSTT/Slipstream is distinct from application
DNS. The carrier core runs on the host; encrypted application DNS does not imply
that the host never resolves a VPN endpoint hostname.

## Dependency diagnosis and upstream downloads

```python
print(manager.dependencies('wireguard'))
print(manager.missing('vless'))
```

These check executable discovery, not version/kernel/server compatibility.
There is no auto-installer UI yet. Upstream projects:

- [Xray releases](https://github.com/XTLS/Xray-core/releases)
- [tun2socks releases](https://github.com/xjasonlyu/tun2socks/releases)
- [tun2socks documentation](https://github.com/xjasonlyu/tun2socks/wiki)
- [DNSTT](https://github.com/Mygod/dnstt)
- [Slipstream Rust](https://github.com/Mygod/slipstream-rust)
