"""IPv4-only, fail-closed namespaces. Never write the host main route table."""
from __future__ import annotations

import argparse
import http.client
import ipaddress
import json
import logging
import os
import socket
import socketserver
import ssl
import struct
import subprocess
import sys
import threading
from pathlib import Path
from urllib.parse import urlsplit

from splitforge.state import Profile


def run(argv: list[str], *, input: str | None = None, check: bool = True,
        timeout: float = 45) -> subprocess.CompletedProcess:
    """Never invoke a shell or include configuration secrets in errors."""
    result = subprocess.run([str(a) for a in argv], input=input, text=True,
                            capture_output=True, timeout=timeout)
    if check and result.returncode:
        raise RuntimeError(f"{Path(argv[0]).name} failed ({result.returncode}); inspect journalctl")
    return result


def require_root():
    if sys.platform != "linux" or os.geteuid() != 0:
        raise PermissionError("This operation requires Linux and root")


def unit_word(value: str) -> str:
    if any(c in value for c in "\n\r\0"):
        raise ValueError("Invalid systemd argument")
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%").replace("$", "$$") + '"'


def namespace_properties(profile: Profile) -> list[str]:
    base = f"/etc/netns/{profile.namespace}"
    return [f"NetworkNamespacePath=/run/netns/{profile.namespace}",
            f"BindReadOnlyPaths={base}/resolv.conf:/etc/resolv.conf {base}/nsswitch.conf:/etc/nsswitch.conf",
            "InaccessiblePaths=-/run/nscd -/run/systemd/resolve/io.systemd.Resolve"]


def atomic_secret(path: Path, content: str, mode: int = 0o600):
    import tempfile
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError("Refusing a symlink destination")
    fd, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


class NetNS:
    def command(self, profile: Profile, *argv: str, **kwargs):
        return run(["ip", "netns", "exec", profile.namespace, *argv], **kwargs)

    def exists(self, profile: Profile) -> bool:
        return Path("/run/netns", profile.namespace).exists()

    def create(self, profile: Profile):
        require_root()
        if not profile.slot:
            raise ValueError("Save the profile before creating its namespace")
        if self.exists(profile):
            raise RuntimeError("Namespace already exists; stop the profile before restarting")
        if Path("/sys/class/net", f"veth-h-{profile.id}").exists():
            raise RuntimeError("Host interface name is already occupied")
        if run(["nft", "list", "table", "inet", f"sf_{profile.id}"], check=False).returncode == 0:
            raise RuntimeError("Host firewall table name is already occupied")
        table, priority = str(20000 + profile.slot), str(12000 + profile.slot)
        existing = json.loads(run(["ip", "-j", "rule", "show"]).stdout)
        occupied = run(["ip", "-4", "route", "show", "table", table], check=False)
        if any(r.get("priority") == int(priority) for r in existing) or occupied.stdout.strip():
            raise RuntimeError("Reserved policy routing slot already occupied")
        # Check every host route table, including connected/container networks.
        routes = json.loads(run(["ip", "-j", "-4", "route", "show", "table", "all"]).stdout)
        for route in routes:
            if route.get("dst", "default") != "default":
                if profile.subnet.overlaps(ipaddress.ip_network(route["dst"], strict=False)):
                    raise RuntimeError(f"Subnet {profile.subnet} conflicts with an existing host route")
        host, peer = f"veth-h-{profile.id}", f"veth-n-{profile.id}"
        try:
            run(["ip", "netns", "add", profile.namespace])
            self.command(profile, "ip", "link", "set", "lo", "up")
            self.command(profile, "sysctl", "-qw", "net.ipv6.conf.all.disable_ipv6=1")
            self.command(profile, "sysctl", "-qw", "net.ipv6.conf.default.disable_ipv6=1")
            # Install the deny policy BEFORE connecting any host link.
            self.guard(profile)
            run(["ip", "link", "add", host, "type", "veth", "peer", "name", peer])
            run(["ip", "link", "set", peer, "netns", profile.namespace])
            run(["sysctl", "-qw", f"net.ipv6.conf.{host}.disable_ipv6=1"])
            # noprefixroute prevents an automatic connected route in host table main.
            run(["ip", "address", "add", f"{profile.gateway}/30", "dev", host, "noprefixroute"])
            run(["ip", "link", "set", host, "up"])
            run(["ip", "route", "add", f"{profile.peer}/32", "dev", host, "scope", "link", "table", table])
            run(["ip", "rule", "add", "priority", priority, "to", f"{profile.peer}/32", "lookup", table])
            self.command(profile, "ip", "address", "add", f"{profile.peer}/30", "dev", peer)
            self.command(profile, "ip", "link", "set", peer, "up")
            # Namespace-to-host traffic is restricted to its proxy port; forwarding
            # is blocked. The scoped NAT rule never changes the host firewall policy.
            run(["nft", "-f", "-"], input=f"""table inet sf_{profile.id} {{
 chain input {{ type filter hook input priority -20; policy accept;
  ip daddr {profile.gateway} iifname != {{ "{host}", "lo" }} drop
  iifname "{host}" ip daddr {profile.gateway} tcp dport 1080 accept
  iifname "{host}" ip daddr {profile.gateway} udp dport 1080 accept
  iifname "{host}" drop
 }}
 chain forward {{ type filter hook forward priority -20; policy accept;
  iifname "{host}" drop
  oifname "{host}" drop
 }}
 chain nat {{ type nat hook postrouting priority srcnat; policy accept;
  ip saddr {profile.subnet} masquerade
 }}
}}\n""")
            directory = Path("/etc/netns", profile.namespace)
            directory.mkdir(mode=0o755, parents=True, exist_ok=True)
            atomic_secret(directory / "resolv.conf", "nameserver 127.0.0.53\noptions timeout:3 attempts:2\n", 0o644)
            # Avoid nss-resolve talking to the host systemd-resolved over AF_UNIX.
            nss = Path("/etc/nsswitch.conf").read_text()
            lines = ["hosts: files dns" if line.lstrip().startswith("hosts:") else line
                     for line in nss.splitlines()]
            atomic_secret(directory / "nsswitch.conf", "\n".join(lines) + "\n", 0o644)
        except BaseException:
            self.destroy(profile)
            raise

    def guard(self, profile: Profile, *, proxy: bool = False, udp: bool = True):
        rules = ""
        if proxy:
            rules = f'ip daddr {profile.gateway} tcp dport 1080 accept\n'
            if udp:
                rules += f'ip daddr {profile.gateway} udp dport 1080 accept\n'
        exists = self.command(profile, "nft", "list", "table", "inet", "splitforge", check=False).returncode == 0
        prefix = "delete table inet splitforge\n" if exists else ""
        block_udp = "meta l4proto udp reject" if not udp else ""
        self.command(profile, "nft", "-f", "-", input=prefix + f"""table inet splitforge {{
 chain input {{ type filter hook input priority 0; policy drop;
  iifname "lo" accept
  ct state established,related accept
 }}
 chain output {{ type filter hook output priority 0; policy drop;
  oifname "lo" accept
  meta nfproto ipv6 drop
  {block_udp}
  oifname "{profile.interface}" accept
  {rules}
 }}
 chain forward {{ type filter hook forward priority 0; policy drop; }}
}}\n""")

    def activate(self, profile: Profile, *, address: str = "198.18.0.1/15", mtu: int = 1400):
        ipaddress.IPv4Interface(address)
        self.command(profile, "ip", "address", "replace", address, "dev", profile.interface)
        self.command(profile, "ip", "link", "set", profile.interface, "mtu", str(mtu), "up")
        self.command(profile, "ip", "route", "replace", "default", "dev", profile.interface)

    def destroy(self, profile: Profile):
        require_root()
        # Do not delete routing slots unless our owned veth exists. This also
        # protects a pre-existing route table when creation fails early.
        host = f"veth-h-{profile.id}"
        if Path("/sys/class/net", host).exists():
            run(["ip", "rule", "del", "priority", str(12000 + profile.slot),
                 "to", f"{profile.peer}/32", "lookup", str(20000 + profile.slot)], check=False)
            run(["ip", "route", "del", f"{profile.peer}/32", "dev", host,
                 "table", str(20000 + profile.slot)], check=False)
            run(["ip", "link", "del", host], check=False)
        run(["nft", "delete", "table", "inet", f"sf_{profile.id}"], check=False)
        run(["ip", "netns", "delete", profile.namespace], check=False)
        # Only remove the two files owned by SplitForge.
        directory = Path("/etc/netns", profile.namespace)
        for name in ("resolv.conf", "nsswitch.conf"):
            (directory / name).unlink(missing_ok=True)
        if directory.exists() and not any(directory.iterdir()):
            directory.rmdir()

    def bandwidth(self, profile: Profile) -> dict[str, int]:
        result = self.command(profile, "ip", "-j", "-s", "link", "show", "dev", profile.interface, check=False)
        if result.returncode:
            return {"rx": 0, "tx": 0}
        stats = json.loads(result.stdout)[0].get("stats64", {})
        return {key: stats.get(key, {}).get("bytes", 0) for key in ("rx", "tx")}


def dns_stub(url: str, bootstrap: str, ca_file: str = ""):
    """Bounded UDP/TCP DNS → certificate-verified DoH, inside the VPN namespace."""
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.fragment:
        raise ValueError("DNS upstream must be a clean HTTPS URL")
    ipaddress.IPv4Address(bootstrap)
    slots = threading.BoundedSemaphore(32)

    def answer(query: bytes) -> bytes:
        if not 12 <= len(query) <= 4096 or query[2] & 0x80:
            return b""
        with slots:
            connection = http.client.HTTPSConnection(parsed.hostname, parsed.port or 443, timeout=8)
            raw = None
            try:
                raw = socket.create_connection((bootstrap, parsed.port or 443), timeout=8)
                connection.sock = ssl.create_default_context(cafile=ca_file or None).wrap_socket(raw, server_hostname=parsed.hostname)
                connection.request("POST", parsed.path or "/dns-query", body=query,
                                   headers={"Content-Type": "application/dns-message", "Accept": "application/dns-message"})
                response = connection.getresponse()
                data = response.read(4097)
                if response.status != 200 or not 12 <= len(data) <= 4096:
                    raise ValueError("Invalid DoH response")
                return query[:2] + data[2:]
            except (OSError, ValueError, http.client.HTTPException) as error:
                logging.getLogger("splitforge.dns").warning("DoH upstream request failed (%s)", type(error).__name__)
                return query[:2] + bytes((0x81, 0x82)) + b"\x00" * 8
            finally:
                connection.close()
                if raw is not None:
                    raw.close()

    def receive(stream: socket.socket, count: int) -> bytes:
        data = b""
        while len(data) < count:
            part = stream.recv(count - len(data))
            if not part:
                raise ConnectionError("Truncated DNS request")
            data += part
        return data

    class UDP(socketserver.BaseRequestHandler):
        def handle(self):
            data, sock = self.request
            reply = answer(data)
            if reply:
                sock.sendto(reply, self.client_address)

    class TCP(socketserver.BaseRequestHandler):
        def handle(self):
            self.request.settimeout(10)
            try:
                while True:
                    length = struct.unpack("!H", receive(self.request, 2))[0]
                    if not 12 <= length <= 4096:
                        return
                    reply = answer(receive(self.request, length))
                    self.request.sendall(struct.pack("!H", len(reply)) + reply)
            except (OSError, ConnectionError):
                return

    class Bounded:
        # Acquire before spawning a handler, bounding threads as well as queries.
        daemon_threads = True
        allow_reuse_address = True
        workers = threading.BoundedSemaphore(32)

        def process_request(self, request, client_address):
            self.workers.acquire()
            try:
                super().process_request(request, client_address)
            except BaseException:
                self.workers.release()
                raise

        def process_request_thread(self, request, client_address):
            try:
                super().process_request_thread(request, client_address)
            finally:
                self.workers.release()

    class UDPServer(Bounded, socketserver.ThreadingUDPServer):
        pass

    class TCPServer(Bounded, socketserver.ThreadingTCPServer):
        pass

    with UDPServer(("127.0.0.53", 53), UDP) as udp, TCPServer(("127.0.0.53", 53), TCP) as tcp:
        threading.Thread(target=udp.serve_forever, daemon=True).start()
        tcp.serve_forever()


def openvpn_up(namespace: str, interface: str):
    """OpenVPN keeps its encrypted transport socket in its birth namespace."""
    from splitforge.state import checked_id
    checked_id(namespace.removeprefix("ns-"))
    if interface != "tun-" + namespace[3:] or os.environ.get("dev") != interface:
        raise ValueError("Unexpected OpenVPN interface")
    local = str(ipaddress.IPv4Address(os.environ["ifconfig_local"]))
    remote = os.environ.get("ifconfig_remote", "")
    netmask = os.environ.get("ifconfig_netmask", "")
    run(["ip", "link", "set", interface, "netns", namespace])
    prefix = ["ip", "netns", "exec", namespace, "ip"]
    if netmask:
        address = str(ipaddress.IPv4Interface(f"{local}/{netmask}"))
        run(prefix + ["address", "replace", address, "dev", interface])
    else:
        remote = str(ipaddress.IPv4Address(remote))
        run(prefix + ["address", "replace", f"{local}/32", "peer", remote, "dev", interface])
    run(prefix + ["link", "set", interface, "up"])
    run(prefix + ["route", "replace", "default", "dev", interface])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["dns", "openvpn-up"])
    parser.add_argument("first")
    parser.add_argument("second")
    parser.add_argument("--ca-file", default="")
    args = parser.parse_args()
    require_root()
    if args.action == "dns":
        dns_stub(args.first, args.second, args.ca_file)
    else:
        openvpn_up(args.first, args.second)
