"""Protocol imports and systemd-owned profile lifecycles.

DNSTT/Slipstream forward TCP to a REMOTE SOCKS5 service, not arbitrary UDP.
Imported Xray JSON must contain exactly one outbound; bypass routes are rejected.
"""
from __future__ import annotations

import argparse
import base64
import dataclasses
import ipaddress
import json
import re
import shlex
import shutil
import socket
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from splitforge.core.netns import NetNS, atomic_secret, namespace_properties, require_root, run, unit_word
from splitforge.state import Profile, StateStore


def decode64(value: str) -> str:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)).decode()


def endpoint(host: str, port: int):
    if not host or any(c.isspace() or ord(c) < 32 for c in host) or not 1 <= port <= 65535:
        raise ValueError("Invalid server endpoint")


def import_uri(uri: str, name: str | None = None) -> Profile:
    uri = uri.strip()
    if uri.startswith("vmess://"):
        item = json.loads(decode64(uri[8:]))
        host, port = item["add"], int(item["port"])
        endpoint(host, port)
        user = {"id": str(uuid.UUID(item["id"])), "alterId": int(item.get("aid", 0)),
                "security": item.get("scy", "auto")}
        outbound = {"protocol": "vmess", "settings": {"vnext": [{"address": host, "port": port, "users": [user]}]}}
        query = {"type": [item.get("net", "tcp")], "security": [item.get("tls") or "none"],
                 "sni": [item.get("sni") or host], "host": [item.get("host", "")],
                 "path": [item.get("path", "/")], "serviceName": [item.get("path", "")]}
        label, protocol = item.get("ps", "vmess"), "vmess"
    else:
        parsed = urlsplit(uri)
        protocol = {"ss": "shadowsocks", "socks": "socks5"}.get(parsed.scheme, parsed.scheme)
        if protocol not in {"vless", "trojan", "shadowsocks", "socks5"}:
            raise ValueError("Unsupported import URI")
        # SIP002 legacy form: ss://base64(method:password@host:port).
        if protocol == "shadowsocks" and "@" not in parsed.netloc:
            parsed = urlsplit("ss://" + decode64(parsed.netloc) +
                              ("?" + parsed.query if parsed.query else "") + "#" + parsed.fragment)
        host, port = parsed.hostname or "", parsed.port or (1080 if protocol == "socks5" else 443)
        endpoint(host, port)
        query = parse_qs(parsed.query, keep_blank_values=True)
        label = unquote(parsed.fragment) or protocol
        server = {"address": host, "port": port}
        if protocol == "shadowsocks":
            if "plugin" in query:
                raise ValueError("SIP003 plugins need an explicit Xray outbound JSON")
            credentials = unquote(parsed.netloc.rsplit("@", 1)[0])
            if ":" not in credentials:
                credentials = decode64(credentials)
            method, password = credentials.split(":", 1)
            server.update(method=method, password=password)
        elif protocol == "socks5":
            if parsed.username is not None:
                server["users"] = [{"user": unquote(parsed.username), "pass": unquote(parsed.password or "")}]
        elif protocol == "trojan":
            server["password"] = unquote(parsed.username or "")
        else:
            user = {"id": str(uuid.UUID(unquote(parsed.username or ""))), "encryption": "none"}
            if query.get("flow", [""])[0]:
                user["flow"] = query["flow"][0]
            server["users"] = [user]
        key = "vnext" if protocol == "vless" else "servers"
        outbound = {"protocol": "socks" if protocol == "socks5" else protocol, "settings": {key: [server]}}

    def option(key: str, default: str = "") -> str:
        return query.get(key, [default])[0]

    transport = option("type", "tcp")
    if transport not in {"tcp", "raw", "ws", "grpc", "httpupgrade", "xhttp"}:
        raise ValueError("Unsupported URI transport; import a native outbound JSON")
    security = option("security", "tls" if protocol == "trojan" else "none")
    if security not in {"none", "tls", "reality"}:
        raise ValueError("Unsupported transport security")
    stream = {"network": transport, "security": security}
    if security == "tls":
        stream["tlsSettings"] = {"serverName": option("sni", host), "fingerprint": option("fp", "chrome")}
        if option("alpn"):
            stream["tlsSettings"]["alpn"] = option("alpn").split(",")
    elif security == "reality":
        if not option("pbk") or not option("sni"):
            raise ValueError("REALITY requires pbk and sni")
        stream["realitySettings"] = {"serverName": option("sni"), "fingerprint": option("fp", "chrome"),
                                     "publicKey": option("pbk"), "shortId": option("sid"), "spiderX": option("spx", "/")}
    if transport in {"ws", "httpupgrade", "xhttp"}:
        settings = {"path": option("path", "/")}
        if option("host"):
            settings["headers" if transport == "ws" else "host"] = ({"Host": option("host")} if transport == "ws" else option("host"))
        stream[transport + "Settings"] = settings
    elif transport == "grpc":
        stream["grpcSettings"] = {"serviceName": option("serviceName"), "multiMode": option("mode") == "multi"}
    outbound["streamSettings"] = stream
    return Profile(name=name or label, protocol=protocol, config={"outbound": outbound})


def wireguard_config(text: str) -> tuple[str, list[str], int]:
    """Parse wg-quick metadata without ever executing its lifecycle hooks."""
    output, addresses, mtu, section, default_peer = [], [], 1420, "", False
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("["):
            if line not in {"[Interface]", "[Peer]"}:
                raise ValueError("Unknown WireGuard section")
            section = line
            output.append(line)
            continue
        key, value = (part.strip() for part in line.split("=", 1))
        if section == "[Interface]" and key in {"PreUp", "PostUp", "PreDown", "PostDown", "SaveConfig", "Table"}:
            raise ValueError(f"WireGuard directive is not allowed: {key}")
        if section == "[Interface]" and key == "Address":
            addresses.extend(str(ipaddress.ip_interface(a.strip())) for a in value.split(","))
        elif section == "[Interface]" and key == "MTU":
            mtu = int(value)
        elif section == "[Interface]" and key == "DNS":
            continue  # SplitForge's certificate-verified DoH stub owns DNS.
        else:
            allowed = ({"PrivateKey", "ListenPort", "FwMark"} if section == "[Interface]" else
                       {"PublicKey", "PresharedKey", "AllowedIPs", "Endpoint", "PersistentKeepalive"})
            if key not in allowed or not section:
                raise ValueError(f"Unknown WireGuard directive: {key}")
            if section == "[Peer]" and key == "AllowedIPs":
                default_peer |= any(ipaddress.ip_network(a.strip(), strict=False) == ipaddress.ip_network("0.0.0.0/0")
                                    for a in value.split(","))
            output.append(f"{key} = {value}")
    ipv4 = [address for address in addresses if ipaddress.ip_interface(address).version == 4]
    if not ipv4 or not 576 <= mtu <= 9000 or not default_peer:
        raise ValueError("WireGuard requires an IPv4 Address and an AllowedIPs=0.0.0.0/0 peer")
    return "\n".join(output) + "\n", ipv4, mtu


OVPN_ALLOWED = set("""client tls-client dev dev-type proto remote remote-random resolv-retry nobind
persist-key persist-tun ca cert key pkcs12 tls-auth tls-crypt tls-crypt-v2 key-direction
remote-cert-tls verify-x509-name cipher data-ciphers data-ciphers-fallback auth auth-user-pass
auth-nocache auth-retry reneg-sec sndbuf rcvbuf tun-mtu mssfix verb mute explicit-exit-notify
connect-retry connect-retry-max connect-timeout server-poll-timeout tls-version-min tls-cipher
tls-ciphersuites ping ping-restart keepalive topology ifconfig route-gateway route-metric
redirect-gateway route route-ipv6 redirect-ipv6 dhcp-option pull-filter pull float
allow-compression peer-fingerprint disable-dco""".split())


def openvpn_config(text: str, base: Path) -> str:
    """Allow-list client options; reject includes, plugins, scripts and daemons."""
    output, block = [], ""
    inline = {"ca", "cert", "key", "tls-auth", "tls-crypt", "tls-crypt-v2", "pkcs12", "auth-user-pass"}
    files = inline
    for raw in text.splitlines():
        line = raw.strip()
        if block:
            output.append(raw)
            if line == f"</{block}>":
                block = ""
            continue
        if not line or line.startswith(("#", ";")):
            continue
        if line.startswith("<"):
            block = line[1:-1]
            if line != f"<{block}>" or block not in inline:
                raise ValueError("Unsupported OpenVPN inline block")
            output.append(line)
            continue
        fields = shlex.split(line, comments=True)
        option = fields[0].removeprefix("--")
        if option not in OVPN_ALLOWED:
            raise ValueError(f"OpenVPN directive is not allowed: {option}")
        if option in {"dev", "dev-type", "redirect-gateway", "route", "route-ipv6", "redirect-ipv6", "dhcp-option", "pull-filter"}:
            continue
        if option in files:
            if len(fields) < 2 or fields[1] == "[inline]":
                raise ValueError("Use an inline block or an explicit credential file")
            path = (base / fields[1]).resolve()
            if not path.is_file():
                raise ValueError(f"Missing OpenVPN credential file: {path.name}")
            fields[1] = str(path)
        output.append(" ".join('"' + f.replace("\\", "\\\\").replace('"', '\\"') + '"' for f in fields))
    if block:
        raise ValueError("Unclosed OpenVPN inline block")
    return "\n".join(output) + "\n"


class ProtocolManager:
    def __init__(self, store: StateStore, netns: NetNS | None = None):
        self.store, self.netns = store, netns or NetNS()

    @staticmethod
    def dependencies(protocol: str) -> list[str]:
        base = ["ip", "nft", "systemctl", "systemd-run", "sysctl"]
        return base + ({"wireguard": ["wg"], "openvpn": ["openvpn"]}.get(
            protocol, ["xray", "tun2socks"] + ({"dnstt": ["dnstt-client"], "slipstream": ["slipstream-client"]}.get(protocol, []))))

    def missing(self, protocol: str) -> list[str]:
        return [name for name in self.dependencies(protocol) if not shutil.which(name)]

    def _save_import(self, profile: Profile, replace_id: str | None = None) -> Profile:
        with self.store.operation():
            if replace_id:
                previous = self.store.profile(replace_id)
                state = run(["systemctl", "show", self._unit(previous), "--property=ActiveState", "--value"], check=False).stdout.strip()
                if self.netns.exists(previous) or state not in {"", "inactive", "failed"}:
                    raise ValueError("Stop the profile before replacing its configuration")
                profile = dataclasses.replace(profile, id=previous.id, slot=previous.slot,
                    doh_url=previous.doh_url, doh_ip=previous.doh_ip,
                    probe_url=previous.probe_url, tls_ca_file=previous.tls_ca_file)
            return self.store.save_profile(profile)

    def import_profile(self, source: str, *, name: str | None = None, replace_id: str | None = None) -> Profile:
        if replace_id and not name:
            name = self.store.profile(replace_id).name
        if "://" in source and not source.lstrip().startswith("{"):
            profile = import_uri(source, name)
        else:
            path = Path(source).expanduser().resolve()
            if path.stat().st_size > 2_000_000:
                raise ValueError("Profile exceeds 2 MB")
            text = path.read_text()
            if path.suffix == ".conf":
                wireguard_config(text)
                profile = Profile(name or path.stem, "wireguard", {"text": text})
            elif path.suffix == ".ovpn":
                profile = Profile(name or path.stem, "openvpn", {"text": openvpn_config(text, path.parent)})
            elif path.suffix == ".json":
                data = json.loads(text)
                outbounds = data.get("outbounds", [data])
                if len(outbounds) != 1 or outbounds[0].get("protocol") not in {"vless", "vmess", "trojan", "shadowsocks", "socks"}:
                    raise ValueError("Import exactly one proxy outbound, without freedom/bypass routes")
                if data.get("routing") or data.get("reverse"):
                    raise ValueError("Custom routing/reverse settings are not accepted")
                profile = Profile(name or path.stem, "xray", {"outbound": outbounds[0]})
            else:
                raise ValueError("Expected .conf, .ovpn, .json or a supported URI")
        return self._save_import(profile, replace_id)

    def dns_tunnel(self, name: str, protocol: str, domain: str, resolver: str,
                   *, public_key: str = "", certificate: str = "", replace_id: str | None = None) -> Profile:
        previous = self.store.profile(replace_id) if replace_id else None
        certificate_text = ""
        if protocol not in {"dnstt", "slipstream"}:
            raise ValueError("Expected dnstt or slipstream")
        if len(domain) > 253 or not re.fullmatch(r"(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}", domain):
            raise ValueError("Invalid tunnel domain")
        if protocol == "dnstt":
            if not public_key and previous and previous.protocol == protocol:
                public_key = previous.config["public_key"]
            if not re.fullmatch(r"[a-fA-F0-9]{64}", public_key):
                raise ValueError("DNSTT needs a 32-byte hex public key")
            if not resolver.startswith(("https://", "tls://", "udp://")):
                raise ValueError("DNSTT resolver must start with https://, tls:// or udp://")
        else:
            host, port = resolver.rsplit(":", 1)
            ipaddress.IPv4Address(host)
            endpoint(host, int(port))
            if certificate and Path(certificate).is_file():
                certificate_text = Path(certificate).read_text(encoding="utf-8")
            elif not certificate and previous and previous.protocol == protocol:
                certificate_text = previous.config["certificate"]
            if not certificate_text:
                raise ValueError("Slipstream requires a pinned server certificate PEM file")
        config = {"domain": domain, "resolver": resolver, "public_key": public_key,
                  "certificate": certificate_text}
        return self._save_import(Profile(name, protocol, config), replace_id)

    def _unit(self, profile: Profile) -> str:
        return f"splitforge-profile-{profile.id}.service"

    def start(self, name: str):
        require_root()
        profile = self.store.profile(name)
        missing = self.missing(profile.protocol)
        if missing:
            raise RuntimeError("Missing dependencies: " + ", ".join(missing))
        command = [sys.executable, "-m", "splitforge.protocols.manager", "--state", str(self.store.path.resolve())]
        content = (f"[Unit]\nDescription=SplitForge profile {profile.id}\nAfter=network-online.target\n"
                   "Wants=network-online.target\n[Service]\nType=oneshot\nRemainAfterExit=yes\n"
                   + "ExecStart=" + " ".join(unit_word(a) for a in [*command, "up", profile.id]) + "\n"
                   + "ExecStop=" + " ".join(unit_word(a) for a in [*command, "down", profile.id]) + "\n"
                   + "TimeoutStartSec=150\nTimeoutStopSec=120\n[Install]\nWantedBy=multi-user.target\n")
        # Do not hold the operation lock while a systemd helper acquires it.
        atomic_secret(Path("/etc/systemd/system", self._unit(profile)), content, 0o644)
        run(["systemctl", "daemon-reload"])
        run(["systemctl", "start", self._unit(profile)], timeout=160)
        run(["systemctl", "enable", self._unit(profile)])

    def stop(self, name: str):
        require_root()
        profile = self.store.profile(name)
        # BindsTo= stops workloads before teardown, leaving no direct fallback.
        run(["systemctl", "stop", self._unit(profile)], timeout=130)
        run(["systemctl", "disable", self._unit(profile)])

    def remove(self, name: str):
        """Remove an unreferenced profile and only its owned system resources."""
        require_root()
        profile = self.store.profile(name)
        snapshot = self.store.snapshot()
        if any(a["profile_id"] == profile.id for a in snapshot["apps"].values()) or profile.id in snapshot["users"].values():
            raise ValueError("Reassign/remove all application and user references first")
        unit = Path("/etc/systemd/system", self._unit(profile))
        if unit.exists():
            self.stop(profile.id)
            unit.unlink()
            run(["systemctl", "daemon-reload"])
        elif self.netns.exists(profile):
            raise ValueError("Inspect the orphan namespace before removing state")
        self.store.delete_profile(profile.id)

    def _service(self, profile: Profile, role: str, argv: list[str], *, namespace: bool = False,
                 restart: bool = True):
        args = ["systemd-run", "--quiet", "--collect", "--service-type=exec",
                f"--unit=splitforge-{role}-{profile.id}",
                "--property=KillMode=control-group", "--property=TimeoutStopSec=10",
                f"--property=PartOf={self._unit(profile)}",
                "--property=Restart=on-failure" if restart else "--property=Restart=no",
                "--property=RestartSec=2"]
        if namespace:
            args.extend(f"--property={setting}" for setting in namespace_properties(profile))
        run([*args, "--", *[a.replace("$", "$$") for a in argv]])

    def _wait_listener(self, profile: Profile, role: str, host: str, port: int):
        """Confirm the listener belongs to our service, avoiding local port races."""
        address = socket.inet_aton(host)[::-1].hex().upper() + f":{port:04X}"
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            result = run(["systemctl", "show", f"splitforge-{role}-{profile.id}.service",
                          "--property=MainPID", "--value"], check=False)
            pid = result.stdout.strip()
            if pid.isdigit() and int(pid) > 0:
                try:
                    sockets = {p.readlink().as_posix() for p in Path(f"/proc/{pid}/fd").iterdir()}
                    for line in Path("/proc/net/tcp").read_text().splitlines()[1:]:
                        fields = line.split()
                        if fields[1] == address and fields[3] == "0A" and f"socket:[{fields[9]}]" in sockets:
                            return
                except (FileNotFoundError, ProcessLookupError):
                    pass
            time.sleep(0.1)
        raise RuntimeError("Expected proxy listener is unavailable or owned by another process")

    def _up(self, profile: Profile):
        require_root()
        with self.store.operation():
            profile = self.store.profile(profile.id)
            runtime = Path("/run/splitforge", profile.id)
            runtime.mkdir(parents=True, mode=0o700, exist_ok=True)
            self.netns.create(profile)
            try:
                if profile.protocol == "wireguard":
                    config, addresses, mtu = wireguard_config(profile.config["text"])
                    path = runtime / "wg.conf"
                    atomic_secret(path, config)
                    run(["ip", "link", "add", profile.interface, "type", "wireguard"])
                    try:
                        run(["wg", "setconf", profile.interface, str(path)])
                        run(["ip", "link", "set", profile.interface, "netns", profile.namespace])
                    except BaseException:
                        run(["ip", "link", "delete", profile.interface], check=False)
                        raise
                    self.netns.activate(profile, address=addresses[0], mtu=mtu)
                    for address in addresses[1:]:
                        self.netns.command(profile, "ip", "address", "add", address, "dev", profile.interface)
                elif profile.protocol == "openvpn":
                    config = runtime / "client.ovpn"
                    atomic_secret(config, profile.config["text"])
                    hook = runtime / "up"
                    atomic_secret(hook, "#!/bin/sh\nexec " + shlex.join([sys.executable, "-m", "splitforge.core.netns",
                                  "openvpn-up", profile.namespace, profile.interface]) + "\n", 0o700)
                    version = re.search(r"OpenVPN (\d+)\.(\d+)", run(["openvpn", "--version"]).stdout)
                    dco = ["--disable-dco"] if version and tuple(map(int, version.groups())) >= (2, 6) else []
                    self._service(profile, "core", ["openvpn", "--config", str(config), "--dev", profile.interface,
                        "--dev-type", "tun", "--route-noexec", "--ifconfig-noexec", "--script-security", "2",
                        "--up", str(hook), "--route-nopull", "--pull-filter", "ignore", "redirect-gateway",
                        "--pull-filter", "ignore", "dhcp-option", "--persist-tun", "--persist-key", "--auth-nocache", *dco], restart=False)
                    self._wait_interface(profile)
                else:
                    self._proxy(profile, runtime)
                self._service(profile, "dns", [sys.executable, "-m", "splitforge.core.netns", "dns",
                                               profile.doh_url, profile.doh_ip,
                                               *(["--ca-file", profile.tls_ca_file] if profile.tls_ca_file else [])], namespace=True)
                self.test(profile.id)
            except BaseException:
                self._down(profile)
                raise

    def _wait_interface(self, profile: Profile):
        deadline = time.monotonic() + 50
        while time.monotonic() < deadline:
            result = self.netns.command(profile, "ip", "-j", "-4", "address", "show", "dev", profile.interface, check=False)
            if result.returncode == 0 and any(i.get("family") == "inet" for i in json.loads(result.stdout)[0].get("addr_info", [])):
                return
            time.sleep(0.2)
        raise TimeoutError("Tunnel interface did not become ready")

    def _proxy(self, profile: Profile, runtime: Path):
        udp = profile.protocol not in {"dnstt", "slipstream"}
        if not udp:
            config = profile.config
            if profile.protocol == "dnstt":
                resolver = config["resolver"]
                flag, address = (("-doh", resolver) if resolver.startswith("https://") else
                                 ("-dot", resolver[6:]) if resolver.startswith("tls://") else ("-udp", resolver[6:]))
                argv = ["dnstt-client", flag, address, "-pubkey", config["public_key"], config["domain"], "127.0.0.1:0"]
            else:
                certificate = runtime / "server.pem"
                atomic_secret(certificate, config["certificate"])
                argv = ["slipstream-client", "--domain", config["domain"], "--resolver", config["resolver"],
                        "--cert", str(certificate), "--tcp-listen-host", "127.0.0.1", "--tcp-listen-port", "0"]
            # Reserve a local transport port briefly. No server is exposed on a
            # wildcard address. Xray bridges to the remote SOCKS5 endpoint.
            with socket.socket() as reservation:
                reservation.bind(("127.0.0.1", 0))
                port = reservation.getsockname()[1]
            argv[-1] = f"127.0.0.1:{port}" if profile.protocol == "dnstt" else str(port)
            self._service(profile, "transport", argv)
            self._wait_listener(profile, "transport", "127.0.0.1", port)
            outbound = {"protocol": "socks", "settings": {"servers": [{"address": "127.0.0.1", "port": port}]}}
        else:
            outbound = profile.config["outbound"]
        # Native configs never supply host routing, inbounds or bypass rules.
        document = {"log": {"loglevel": "warning"}, "inbounds": [{"listen": profile.gateway, "port": 1080,
                    "protocol": "socks", "settings": {"auth": "noauth", "udp": udp, "ip": profile.gateway}}],
                    "outbounds": [dict(outbound, tag="tunnel")]}
        config_path = runtime / "xray.json"
        atomic_secret(config_path, json.dumps(document))
        run(["xray", "run", "-test", "-config", str(config_path)])
        self._service(profile, "core", ["xray", "run", "-config", str(config_path)])
        self._wait_listener(profile, "core", profile.gateway, 1080)
        self.netns.command(profile, "ip", "tuntap", "add", "dev", profile.interface, "mode", "tun")
        self.netns.guard(profile, proxy=True, udp=udp)
        self.netns.activate(profile)
        self._service(profile, "tun", ["tun2socks", "--device", f"tun://{profile.interface}", "--proxy",
                                      f"socks5://{profile.gateway}:1080", "--loglevel", "warn"], namespace=True)

    def _down(self, profile: Profile):
        require_root()
        with self.store.operation():
            for role in ("dns", "tun", "core", "transport"):
                run(["systemctl", "stop", f"splitforge-{role}-{profile.id}.service"], check=False, timeout=15)
            self.netns.destroy(profile)
            runtime = Path("/run/splitforge", profile.id)
            if runtime.exists():
                shutil.rmtree(runtime)

    def test(self, name: str, *, persist: bool = True) -> dict:
        profile = self.store.profile(name)
        if not self.netns.exists(profile):
            raise RuntimeError("Start the profile before testing")
        # End-to-end HTTPS also exercises the namespace DNS stub. No direct
        # host HTTP fallback, redirects, GeoIP request or inherited proxy env.
        script = ("import json,ssl,urllib.request; "
                  f"c=ssl.create_default_context(cafile={profile.tls_ca_file or None!r}); "
                  "o=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPSHandler(context=c)); "
                  f"r=o.open({profile.probe_url!r},timeout=8); "
                  "d=dict(l.split('=',1) for l in r.read(8192).decode().splitlines() if '=' in l); "
                  "print(json.dumps({'ip':d['ip'],'country':d.get('loc','')}))")
        deadline, start = time.monotonic() + 25, time.monotonic()
        while True:
            properties = [f"--property={setting}" for setting in namespace_properties(profile)]
            result = run(["systemd-run", "--quiet", "--wait", "--pipe", "--collect", "--service-type=exec",
                          f"--unit=splitforge-probe-{uuid.uuid4().hex[:8]}", "--property=RuntimeMaxSec=10",
                          *properties, "--", sys.executable, "-c", script.replace("$", "$$")], timeout=15, check=False)
            if result.returncode == 0:
                break
            if time.monotonic() >= deadline:
                raise RuntimeError("Tunnel egress/DNS test failed; no host fallback was used")
            time.sleep(0.3)
        response = json.loads(result.stdout)
        ip = str(ipaddress.IPv4Address(response["ip"]))
        country = response["country"] if re.fullmatch(r"[A-Z]{2}", response["country"]) else ""
        latency = round((time.monotonic() - start) * 1000, 1)
        if persist:
            profile.exit_ip, profile.latency_ms, profile.country = ip, latency, country
            self.store.save_profile(profile)
        return {"exit_ip": ip, "country": country, "latency_ms": latency, "measurement": "HTTPS + DNS, not ICMP"}

    def status(self, name: str) -> dict:
        profile = self.store.profile(name)
        active = run(["systemctl", "is-active", "--quiet", self._unit(profile)], check=False).returncode == 0
        return {"id": profile.id, "name": profile.name, "active": active,
                "namespace": self.netns.exists(profile), "exit_ip": profile.exit_ip,
                "latency_ms": profile.latency_ms,
                "bandwidth": self.netns.bandwidth(profile) if self.netns.exists(profile) else {"rx": 0, "tx": 0}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", default="/etc/splitforge/state.json")
    parser.add_argument("action", choices=["up", "down"])
    parser.add_argument("profile")
    args = parser.parse_args()
    manager = ProtocolManager(StateStore(args.state))
    profile = manager.store.profile(args.profile)
    if args.action == "up":
        manager._up(profile)
    else:
        manager._down(profile)
