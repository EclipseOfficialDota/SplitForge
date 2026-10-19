"""Locked, atomic, versioned state. Configuration is secret and root-owned."""
from __future__ import annotations

import copy
import ipaddress
import json
import os
import re
import tempfile
import threading
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePosixPath
from typing import Iterator
from urllib.parse import urlsplit

ID = re.compile(r"^[0-9a-f]{8}$")
PROTOCOLS = {"vless", "vmess", "trojan", "shadowsocks", "xray",
             "wireguard", "openvpn", "dnstt", "slipstream", "socks5"}


def checked_id(value: str) -> str:
    if not ID.fullmatch(value):
        raise ValueError("Invalid SplitForge ID")
    return value


@dataclass
class Profile:
    name: str
    protocol: str
    config: dict
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    slot: int = 0
    doh_url: str = "https://cloudflare-dns.com/dns-query"
    doh_ip: str = "1.1.1.1"
    exit_ip: str = ""
    country: str = ""
    latency_ms: float | None = None
    probe_url: str = "https://www.cloudflare.com/cdn-cgi/trace"
    tls_ca_file: str = ""

    def __post_init__(self):
        checked_id(self.id)
        if self.protocol not in PROTOCOLS or not isinstance(self.config, dict):
            raise ValueError("Unknown protocol or invalid configuration")
        if not self.name.strip() or len(self.name) > 80 or any(ord(c) < 32 for c in self.name):
            raise ValueError("Profile name must contain 1–80 printable characters")
        if not 0 <= self.slot <= 4095:
            raise ValueError("Invalid subnet slot")
        ipaddress.IPv4Address(self.doh_ip)
        dns = urlsplit(self.doh_url)
        if dns.scheme != "https" or not dns.hostname or dns.username or dns.fragment or dns.query:
            raise ValueError("DNS upstream must be an HTTPS URL without credentials, query or fragment")
        probe = urlsplit(self.probe_url)
        if probe.scheme != "https" or not probe.hostname or probe.username or probe.fragment:
            raise ValueError("Egress probe must use HTTPS without credentials or fragment")
        if self.tls_ca_file and (not PurePosixPath(self.tls_ca_file).is_absolute() or any(c in self.tls_ca_file for c in "\r\n\0")):
            raise ValueError("Custom CA bundle must use an absolute path")

    @property
    def namespace(self) -> str:
        return f"ns-{self.id}"

    @property
    def interface(self) -> str:
        return ("wg-" if self.protocol == "wireguard" else "tun-") + self.id

    @property
    def subnet(self) -> ipaddress.IPv4Network:
        return ipaddress.IPv4Network((int(ipaddress.IPv4Address("10.203.0.0")) + self.slot * 4, 30))

    @property
    def gateway(self) -> str:
        return str(self.subnet.network_address + 1)

    @property
    def peer(self) -> str:
        return str(self.subnet.network_address + 2)


@dataclass
class AppBinding:
    name: str
    argv: list[str] = field(default_factory=list)
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    profile_id: str | None = None
    user: str = "nobody"
    cwd: str = "/"
    service: str | None = None
    kill_switch: bool = True
    isolate_dns: bool = True
    enabled: bool = False
    primary_profile_id: str | None = None
    backup_profile_id: str | None = None
    failover_enabled: bool = False

    def __post_init__(self):
        checked_id(self.id)
        if self.profile_id is not None:
            checked_id(self.profile_id)
        for profile_id in (self.primary_profile_id, self.backup_profile_id):
            if profile_id is not None:
                checked_id(profile_id)
        if not isinstance(self.failover_enabled, bool):
            raise ValueError('Failover enabled must be a boolean')
        if self.failover_enabled and (not self.primary_profile_id or not self.backup_profile_id
                                     or self.primary_profile_id == self.backup_profile_id
                                     or self.profile_id not in {self.primary_profile_id, self.backup_profile_id}
                                     or not self.kill_switch or not self.isolate_dns):
            raise ValueError('Automatic failover requires distinct primary/backup tunnels and a tunneled assignment')
        if not self.name.strip() or any(ord(c) < 32 for c in self.name):
            raise ValueError("Invalid application name")
        if not self.service and not self.argv:
            raise ValueError("Supply an executable command or an existing service")
        if self.argv and (not PurePosixPath(self.argv[0]).is_absolute() or
                          any(not isinstance(a, str) or "\0" in a or "\n" in a or "\r" in a for a in self.argv)):
            raise ValueError("Command must use an absolute executable and valid arguments")
        if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_-]*\$?", self.user):
            raise ValueError("Invalid Linux user name")
        if not PurePosixPath(self.cwd).is_absolute() or any(c in self.cwd for c in "\n\r\0"):
            raise ValueError("Working directory must be absolute")
        if self.service and (not re.fullmatch(r"[A-Za-z0-9_@.:-]+\.service", self.service)
                             or self.service.startswith("-")):
            raise ValueError("Invalid systemd service name")

    @property
    def profile_references(self):
        return {value for value in (self.profile_id, self.primary_profile_id, self.backup_profile_id) if value}


class StateStore:
    def __init__(self, path: str | Path = "/etc/splitforge/state.json"):
        self.path = Path(path)
        self._mutex = threading.RLock()
        self._depth = threading.local()

    @contextmanager
    def operation(self, scope: str = "state") -> Iterator[None]:
        """Serialize state AND system mutations across threads/processes."""
        import fcntl
        suffix = ".lock" if scope == "state" else f".{checked_id(scope)}.lock"
        with self._mutex:
            active = getattr(self._depth, "active", set())
            if scope in active:
                yield
                return
            self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            if self.path.parent.is_symlink() or self.path.is_symlink():
                raise RuntimeError("State paths must not be symbolic links")
            fd = os.open(str(self.path) + suffix, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX)
                self._depth.active = active | {scope}
                yield
            finally:
                self._depth.active = active
                fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)

    def _read(self) -> dict:
        if self.path.is_symlink():
            raise RuntimeError("State file must not be a symbolic link")
        if not self.path.exists():
            return {"version": 1, "profiles": {}, "apps": {}, "users": {}}
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if data.get("version") != 1:
            raise ValueError("Unsupported state version; refusing to overwrite")
        for key, item in data["profiles"].items():
            if Profile(**item).id != key:
                raise ValueError("Profile key mismatch")
        for key, item in data["apps"].items():
            app = AppBinding(**item)
            if app.id != key or not app.profile_references.issubset(data['profiles']):
                raise ValueError("Invalid application reference")
        slots = [p["slot"] for p in data["profiles"].values()]
        if 0 in slots or len(slots) != len(set(slots)):
            raise ValueError("Duplicate or unallocated subnet")
        if any(profile_id not in data["profiles"] for profile_id in data["users"].values()):
            raise ValueError("Invalid per-user profile reference")
        return data

    def _write(self, data: dict):
        fd, name = tempfile.mkstemp(dir=self.path.parent, prefix=".state-")
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(data, stream, indent=2, ensure_ascii=False)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.path)
            directory = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            Path(name).unlink(missing_ok=True)

    def snapshot(self) -> dict:
        # Atomic replace gives readers a coherent old/new document without
        # blocking TUI refreshes behind a slow tunnel startup.
        return copy.deepcopy(self._read())

    def profiles(self) -> list[Profile]:
        return [Profile(**p) for p in self.snapshot()["profiles"].values()]

    def apps(self) -> list[AppBinding]:
        return [AppBinding(**a) for a in self.snapshot()["apps"].values()]

    def profile(self, name_or_id: str) -> Profile:
        matches = [p for p in self.profiles() if name_or_id in (p.id, p.name)]
        if len(matches) != 1:
            raise KeyError(f"Profile not found or ambiguous: {name_or_id}")
        return matches[0]

    def app(self, app_id: str) -> AppBinding:
        return AppBinding(**self.snapshot()["apps"][checked_id(app_id)])

    def save_profile(self, profile: Profile) -> Profile:
        Profile(**asdict(profile))
        with self.operation():
            data = self._read()
            others = [p for key, p in data["profiles"].items() if key != profile.id]
            if any(p["name"] == profile.name for p in others):
                raise ValueError("Profile name already exists")
            previous = data["profiles"].get(profile.id)
            if previous:
                profile.slot = previous["slot"]
            elif not profile.slot:
                used = {p["slot"] for p in others}
                profile.slot = next((n for n in range(1, 4096) if n not in used), 0)
            if not profile.slot or any(p["slot"] == profile.slot for p in others):
                raise ValueError("Subnet pool exhausted or slot occupied")
            data["profiles"][profile.id] = asdict(profile)
            self._write(data)
        return profile

    def save_app(self, app: AppBinding):
        AppBinding(**asdict(app))
        with self.operation():
            data = self._read()
            if not app.profile_references.issubset(data['profiles']):
                raise ValueError("Unknown assigned profile")
            data["apps"][app.id] = asdict(app)
            self._write(data)

    def delete_profile(self, profile_id: str):
        with self.operation():
            data = self._read()
            if any(profile_id in AppBinding(**a).profile_references for a in data["apps"].values()) or profile_id in data["users"].values():
                raise ValueError("Profile is still assigned")
            del data["profiles"][checked_id(profile_id)]
            self._write(data)

    def delete_app(self, app_id: str):
        with self.operation():
            data = self._read()
            del data["apps"][checked_id(app_id)]
            self._write(data)

    def assign_user(self, user: str, profile_id: str | None):
        with self.operation():
            data = self._read()
            if profile_id is not None:
                if profile_id not in data["profiles"]:
                    raise KeyError(profile_id)
                data["users"][user] = profile_id
            else:
                data["users"].pop(user, None)
            self._write(data)
