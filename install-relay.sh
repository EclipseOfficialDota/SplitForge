#!/usr/bin/env bash
# Install the destination relay without running the VPS network/core installer.
set -euo pipefail
umask 022
if [[ ${EUID} -ne 0 ]]; then
    echo 'Run with sudo bash install-relay.sh' >&2
    exit 1
fi
version='2.10.2'
prefix='/opt/splitforge-relay'
release="https://github.com/EclipseOfficialDota/SplitForge/releases/download/v${version}"
apt-get update
apt-get install -y --no-install-recommends python3-venv ca-certificates curl
temporary=$(mktemp -d)
trap 'rm -rf -- "$temporary"' EXIT
wheel="splitforge-${version}-py3-none-any.whl"
curl --fail --location --retry 3 "$release/$wheel" -o "$temporary/$wheel"
curl --fail --location --retry 3 "$release/SHA256SUMS" -o "$temporary/SHA256SUMS"
python3 - "$temporary" "$wheel" <<'PY'
import hashlib, pathlib, sys
folder, name = pathlib.Path(sys.argv[1]), sys.argv[2]
entries = [line.split() for line in (folder / 'SHA256SUMS').read_text().splitlines()]
matches = [digest for digest, filename in entries if filename == name]
if len(matches) != 1 or hashlib.sha256((folder / name).read_bytes()).hexdigest() != matches[0]:
    raise SystemExit('Relay wheel checksum verification failed')
PY
if [[ -L "$prefix" || -L "$prefix/venv" ]]; then
    echo 'Refusing a linked relay installation path' >&2
    exit 1
fi
install -d -m 0755 "$prefix"
python3 -m venv "$prefix/venv"
"$prefix/venv/bin/python" -m pip install 'cryptography>=46,<51'
"$prefix/venv/bin/python" -m pip install --no-deps --upgrade "$temporary/$wheel"
"$prefix/venv/bin/python" -m splitforge.core.bond setup
systemctl is-active --quiet splitforge-bond-relay.service
echo 'Ready. Read /etc/splitforge/relay.json privately and copy its token into the SplitForge bond form.'
