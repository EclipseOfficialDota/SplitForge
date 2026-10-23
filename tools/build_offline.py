"""Build one native Ubuntu/Debian offline release inside a clean container."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import zipfile


PACKAGES = [
    'git', 'python3', 'python3-venv', 'ca-certificates', 'curl', 'unzip',
    'iproute2', 'nftables', 'procps', 'wireguard-tools', 'openvpn',
    'proxychains4', 'nginx',
]


def run(*args, **kwargs):
    subprocess.run(args, check=True, **kwargs)


def checksums(folder: Path):
    """Cover every payload file; the outer release also hashes the ZIP itself."""
    rows = []
    for path in sorted(folder.rglob('*')):
        if path.is_symlink():
            raise ValueError('Offline payload must not contain symlinks')
        if path.is_file() and path.name != 'SHA256SUMS':
            digest = hashlib.sha256()
            with path.open('rb') as stream:
                for chunk in iter(lambda: stream.read(1048576), b''):
                    digest.update(chunk)
            rows.append(f'{digest.hexdigest()}  {path.relative_to(folder).as_posix()}\n')
    (folder / 'SHA256SUMS').write_text(''.join(rows))


def main():
    try:
        import tomllib
    except ImportError:  # Ubuntu 22.04 / Python 3.10 build host.
        import tomli as tomllib
    source, output = map(Path, sys.argv[1:])
    version = tomllib.loads((source / 'pyproject.toml').read_text())['project']['version']
    release = dict(line.split('=', 1) for line in Path('/etc/os-release').read_text().splitlines() if '=' in line)
    distro, distro_version = (release[key].strip('"') for key in ('ID', 'VERSION_ID'))
    arch = subprocess.check_output(['dpkg', '--print-architecture'], text=True).strip()
    name = f'splitforge-{version}-offline-{distro}-{distro_version}-{arch}'
    folder = Path('/tmp') / name
    folder.mkdir()  # Refuse stale builds rather than mixing payloads.
    wheels, debs, binaries, sources = (folder / part for part in ('wheels', 'debs', 'bin', 'sources'))
    for directory in (wheels, debs, binaries, sources):
        directory.mkdir()
    (folder / 'TARGET').write_text(f'{distro} {distro_version} {arch}\n')
    shutil.copy2(source / 'install-offline.sh', folder)
    for filename in ('LICENSE', 'requirements.lock'):
        shutil.copy2(source / filename, folder)
    shutil.copy2(source / 'docs/OFFLINE.md', folder / 'README.md')

    # An empty package status includes the complete dependency closure, including
    # libraries already present in this build image but absent on a fresh VPS.
    status = Path('/tmp/splitforge-empty-status')
    status.touch()
    run('apt-get', 'update')
    run('apt-get', '-y', '--download-only', '--no-install-recommends',
        '-o', f'Dir::State::status={status}', '-o', f'Dir::Cache::archives={debs}',
        'install', *PACKAGES)
    shutil.rmtree(debs / 'partial', ignore_errors=True)
    (debs / 'lock').unlink(missing_ok=True)

    # Native Python and ABI-specific wheels for this exact OS/architecture.
    run('python3', '-m', 'venv', '/tmp/splitforge-build-venv')
    python = '/tmp/splitforge-build-venv/bin/python'
    run(python, '-m', 'pip', 'install', 'build')
    run(python, '-m', 'build', '--outdir', str(sources), str(source))
    wheel = next(sources.glob('splitforge-*.whl'))
    run(python, '-m', 'pip', 'download', '--only-binary=:all:', '--dest', str(wheels),
        '--constraint', str(source / 'requirements.lock'), str(wheel),
        'certbot>=5.4,<6', 'setuptools>=77', 'wheel')
    run(python, '-m', 'pip', 'install', '--no-index', '--find-links', str(wheels), str(wheel))
    wheel.unlink()  # pip copied the distribution into wheels/.

    # Reuse the pinned, checksum-verifying core installer. DNS cores are built
    # here, so the destination never needs Go, source hosts or module mirrors.
    # The installer imports pydantic; run the core build in the prepared venv.
    core_script = (
        'from pathlib import Path; from splitforge.core import dependencies; '
        f'destination = Path({str(binaries)!r}); '
        '[print(dependencies.install(name, destination=destination), flush=True) '
        'for name in ("xray", "tun2socks", "slipstream-client", "dnstt-client", "noizdns-client")]'
    )
    os.environ['SPLITFORGE_DOWNLOAD_CACHE'] = str(sources)
    os.environ['GOMODCACHE'] = '/tmp/splitforge-go-modules'
    run(python, '-c', core_script)
    # Read the constants without importing the runtime into the bootstrap venv.
    constants = subprocess.check_output([python, '-c',
        'import json; from splitforge.core import dependencies as d; '
        'print(json.dumps([d.DNSTT_REVISION, d.NOIZDNS_REVISION, d.NOIZDNS_DNSTT_REVISION]))'], text=True)
    import json
    dnstt_revision, noiz_revision, companion_revision = json.loads(constants)
    # Preserve upstream archives (licenses/source) alongside the built clients.
    for cached in Path('/var/cache/splitforge-downloads').iterdir():
        if cached.is_file() and not cached.name.startswith('.'):
            shutil.copy2(cached, sources / cached.name)
    modules = Path(os.environ['GOMODCACHE'])
    if modules.exists():
        with tarfile.open(sources / 'go-modules.tar.gz', 'w:gz') as archive:
            archive.add(modules, arcname='gomodcache')
    (sources / 'NOTICE.txt').write_text(
        'Third-party components retain their upstream licenses.\n'
        'Debian packages include /usr/share/doc/*/copyright; Python wheels include license metadata.\n'
        'Xray: https://github.com/XTLS/Xray-core\n'
        'tun2socks: https://github.com/xjasonlyu/tun2socks\n'
        'Slipstream: https://github.com/Mygod/slipstream-rust\n'
        'DNSTT: https://github.com/Mygod/dnstt\n'
        'NoizDNS (AGPL): https://github.com/anonvector/noizdns\n'
        f'DNSTT source: {dnstt_revision}\n'
        f'NoizDNS source: {noiz_revision}\n'
        f'NoizDNS companion: {companion_revision}\n'
        'DNS client build: CGO_ENABLED=0 GOTOOLCHAIN=local go build -trimpath.\n'
        'Pinned source archives, Go toolchain and module sources are included.\n')
    checksums(folder)
    output.mkdir(parents=True, exist_ok=True)
    target = output / (name + '.zip')
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(folder.rglob('*')):
            if path.is_file():
                archive.write(path, path.relative_to(folder.parent))
    print(target, flush=True)


if __name__ == '__main__':
    main()
