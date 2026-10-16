"""Official, pinned release downloads with SHA-256 verification."""
from __future__ import annotations

import hashlib
import io
import os
import platform
import re
import shutil
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from splitforge.core.netns import require_root, run

RELEASES = {
    "xray": ("XTLS/Xray-core", "v26.3.27", {
        "x86_64": ("Xray-linux-64.zip", "23cd9af937744d97776ee35ecad4972cf4b2109d1e0fe6be9930467608f7c8ae"),
        "aarch64": ("Xray-linux-arm64-v8a.zip", "4d30283ae614e3057f730f67cd088a42be6fdf91f8639d82cb69e48cde80413c"),
    }),
    "tun2socks": ("xjasonlyu/tun2socks", "v2.7.0", {
        "x86_64": ("tun2socks-linux-amd64.zip", "a612baa287a3b6de6221f74fd02b442a50888508227ecf51e1288a5ccbb77381"),
        "aarch64": ("tun2socks-linux-arm64.zip", "3931476c9cfa8fa236d23aeaf36767df0eb27cc11ecaab699faba57744450f49"),
    }),
    "slipstream-client": ("Mygod/slipstream-rust", "v0.1.1", {
        "x86_64": ("slipstream-linux-x86_64.tar.gz", "5572d407d685a4a87e4de5a7121566d48ac719068e50ad69705793dc6d9ff682"),
        "aarch64": ("slipstream-linux-arm64.tar.gz", "4220db98c49617c8453514afe6ea7455ccc6f31aad14f206643e9d81cd9b7e31"),
    }),
}
PACKAGES = {
    "base": ["iproute2", "nftables", "procps", "ca-certificates"],
    "wireguard": ["wireguard-tools"], "openvpn": ["openvpn"],
    "proxychains4": ["proxychains4"],
}
COMPONENTS = {
    "base": (("ip", "nft", "sysctl"), "Linux network tools / ابزارهای پایه"),
    "xray": (("xray",), "VLESS, VMess, REALITY, Trojan, Shadowsocks, SOCKS5"),
    "tun2socks": (("tun2socks",), "TUN bridge for proxy profiles / پل شبکه پروکسی"),
    "wireguard": (("wg",), "WireGuard profiles / پروفایل وایرگارد"),
    "openvpn": (("openvpn",), "OpenVPN profiles / پروفایل اوپن وی پی ان"),
    "dnstt-client": (("dnstt-client",), "DNSTT DNS tunnel / تونل دی ان اس"),
    "slipstream-client": (("slipstream-client",), "Slipstream DNS tunnel / تونل دی ان اس"),
    "proxychains4": (("proxychains4",), "Optional TCP wrapper / حالت اختیاری TCP"),
}


def component_plan(names) -> list[str]:
    """Include the network tools and proxy helpers required by selected cores."""
    selected = set(names)
    if selected - COMPONENTS.keys():
        raise ValueError("Unknown dependency selection")
    if selected & {"xray", "tun2socks", "dnstt-client", "slipstream-client"}:
        selected.update({"xray", "tun2socks"})
    if selected:
        selected.add("base")
    return [name for name in COMPONENTS if name in selected]


def component_installed(name: str) -> bool:
    """Executable discovery only; this does not certify versions or connectivity."""
    return all(shutil.which(binary) for binary in COMPONENTS[name][0])


DNSTT_REVISION = "17aa1fed864cd5493e3d09a14df1b8b5cc1df123"
DNSTT_SHA256 = "d68bb4838133aa363436117c8a80d8899146a122f24a61aae1cd417d7913b9dc"
GO_VERSION = "go1.26.1"
GO_DIGESTS = {"x86_64": ("amd64", "031f088e5d955bab8657ede27ad4e3bc5b7c1ba281f05f245bcc304f327c987a"),
              "aarch64": ("arm64", "a290581cfe4fe28ddd737dde3095f3dbeb7f2e4065cab4eae44dfc53b760c2f7")}


def download(url: str, expected: str, limit: int) -> bytes:
    """Accept a pre-fetched offline artifact only after the same digest check."""
    cache = os.environ.get("SPLITFORGE_DOWNLOAD_CACHE")
    cached = Path(cache) / url.rsplit("/", 1)[-1] if cache else None
    if cached and cached.is_symlink():
        raise ValueError("Download cache entries must not be symlinks")
    if cached and cached.is_file():
        if cached.stat().st_size > limit:
            raise RuntimeError("Cached release exceeds size limit")
        data = cached.read_bytes()
    else:
        request = urllib.request.Request(url, headers={"User-Agent": "SplitForge/2.0"})
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                data = response.read(limit + 1)
        except OSError as error:
            raise RuntimeError(f"Download failed for {url.rsplit('/', 1)[-1]}; check upstream access or provide a verified offline cache") from error
    if len(data) > limit or hashlib.sha256(data).hexdigest() != expected:
        raise RuntimeError("Release/source checksum verification failed; nothing installed")
    return data


def unpack_verified_tar(data: bytes, base: Path):
    base = base.resolve()
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        total = 0
        for member in archive.getmembers():
            total += member.size
            target = (base / member.name).resolve()
            if not target.is_relative_to(base) or member.issym() or member.islnk() or total > 600_000_000:
                raise RuntimeError("Unsafe source/toolchain archive entry")
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            elif member.isfile():
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(member) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)
                os.chmod(target, member.mode & 0o755)
            else:
                raise RuntimeError("Unsupported archive entry")


def install_dnstt(destination: Path) -> str:
    url = f"https://codeload.github.com/Mygod/dnstt/tar.gz/{DNSTT_REVISION}"
    data = download(url, DNSTT_SHA256, 5_000_000)
    with tempfile.TemporaryDirectory(prefix="splitforge-dnstt-") as directory:
        base = Path(directory).resolve()
        unpack_verified_tar(data, base)
        roots = [p.parent for p in base.glob("*/go.mod")]
        if len(roots) != 1:
            raise RuntimeError("Unexpected DNSTT source layout")
        binary = base / "dnstt-client"
        compiler = shutil.which("go")
        version = run([compiler, "version"], check=False).stdout if compiler else ""
        match = re.search(r"go(\d+)\.(\d+)(?:\.(\d+))?", version)
        if not match or tuple(int(n or 0) for n in match.groups()) < (1, 24, 4):
            arch = {"amd64": "x86_64", "arm64": "aarch64"}.get(platform.machine(), platform.machine())
            if arch not in GO_DIGESTS:
                raise ValueError("Install Go 1.24.4+ manually for this CPU architecture")
            go_arch, digest = GO_DIGESTS[arch]
            toolchain = download(f"https://go.dev/dl/{GO_VERSION}.linux-{go_arch}.tar.gz", digest, 150_000_000)
            unpack_verified_tar(toolchain, base)
            compiler = str(base / "go/bin/go")
        proxy = os.environ.get("GOPROXY", "https://proxy.golang.org|direct")
        result = run(["env", "GOTOOLCHAIN=local", "CGO_ENABLED=0", f"GOPROXY={proxy}", compiler,
                      "-C", str(roots[0]), "build", "-trimpath", "-o", str(binary), "./dnstt-client"], timeout=600, check=False)
        if result.returncode:
            from splitforge.core.netns import atomic_secret
            log = Path("/var/log/splitforge-install.log")
            atomic_secret(log, result.stdout + result.stderr)
            raise RuntimeError(f"DNSTT source build failed; private diagnostics: {log}")
        destination.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=destination, prefix=".splitforge-dnstt-")
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(binary.read_bytes())
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary, 0o755)
            os.replace(temporary, destination / "dnstt-client")
        finally:
            Path(temporary).unlink(missing_ok=True)
    return f"Built dnstt-client from SHA-256-verified source {DNSTT_REVISION[:12]}"


def install(name: str, destination: Path = Path("/usr/local/bin")) -> str:
    require_root()
    if name == "dnstt-client":
        return install_dnstt(destination)
    if name in PACKAGES:
        run(["apt-get", "update"], timeout=180)
        run(["env", "DEBIAN_FRONTEND=noninteractive", "apt-get", "install", "-y",
             "--no-install-recommends", *PACKAGES[name]], timeout=300)
        return "Installed " + name
    if name not in RELEASES:
        raise ValueError("No verified binary release is registered for this dependency; use its official source build")
    repository, version, assets = RELEASES[name]
    arch = {"amd64": "x86_64", "arm64": "aarch64"}.get(platform.machine(), platform.machine())
    if arch not in assets:
        raise ValueError("Automatic downloads support Linux x86_64 and aarch64")
    filename, expected = assets[arch]
    data = download(f"https://github.com/{repository}/releases/download/{version}/{filename}", expected, 100_000_000)
    # Read just the intended regular executable; never extract archive paths.
    if filename.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            matches = [n for n in archive.namelist() if Path(n).name == name or
                       (name == "tun2socks" and Path(n).name.startswith("tun2socks-linux-"))]
            if len(matches) != 1:
                raise RuntimeError("Unexpected release archive layout")
            executable = archive.read(matches[0])
    else:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
            matches = [m for m in archive.getmembers() if m.isfile() and Path(m.name).name == name]
            if len(matches) != 1:
                raise RuntimeError("Unexpected release archive layout")
            executable = archive.extractfile(matches[0]).read()
    if not executable.startswith(b"\x7fELF"):
        raise RuntimeError("Release did not contain a Linux ELF executable")
    destination.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=destination, prefix=".splitforge-")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(executable)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o755)
        os.replace(temporary, destination / name)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return f"Installed {name} {version} ({arch}, SHA-256 verified)"
