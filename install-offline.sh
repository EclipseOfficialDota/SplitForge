#!/usr/bin/env bash
# Run from an extracted, matching official offline Release ZIP.
set -Eeuo pipefail
umask 022
prefix=/opt/splitforge
upgrade=0
restore=0
while (($#)); do
  case "$1" in
    --prefix) prefix=${2:?Missing prefix}; shift 2 ;;
    --upgrade) upgrade=1; shift ;;
    --restore) restore=1; shift ;;
    *) printf 'Usage: sudo bash install-offline.sh [--prefix /opt/splitforge] [--upgrade] [--restore]\n' >&2; exit 2 ;;
  esac
done
[[ $EUID -eq 0 ]] || { echo 'Run with sudo/root.' >&2; exit 1; }
[[ $prefix == /* && $prefix != / && $prefix != *$'\n'* && ! -L $prefix && ! -L $prefix/venv ]] || {
  echo 'Invalid installation prefix.' >&2; exit 2;
}
folder=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
cd -- "$folder"
[[ -f TARGET && -f SHA256SUMS ]] || { echo 'Extract a complete official offline Release ZIP first.' >&2; exit 1; }
sha256sum --check --strict SHA256SUMS
read -r target_id target_version target_arch < TARGET
source /etc/os-release
[[ $ID == "$target_id" && $VERSION_ID == "$target_version" && $(dpkg --print-architecture) == "$target_arch" ]] || {
  echo 'Wrong offline ZIP: distribution, version and architecture must all match.' >&2; exit 1;
}
if [[ -x $prefix/venv/bin/splitforge ]]; then
  ((upgrade)) || { echo 'Existing installation: use --upgrade.' >&2; exit 1; }
  "$prefix/venv/bin/splitforge" stop-all --preserve
fi
export DEBIAN_FRONTEND=noninteractive
# Only local .debs: never update package lists or fall back to a mirror.
install -d -m 0755 /var/cache/apt/archives/partial
# --no-download also disables apt's normal staging of local file arguments.
# Populate its cache first so dpkg receives absolute, available archive paths.
cp -- "$folder"/debs/*.deb /var/cache/apt/archives/
apt-get -y --no-download --no-install-recommends install "$folder"/debs/*.deb
install -d -m 0755 -- "$prefix"
python3 -m venv "$prefix/venv"
"$prefix/venv/bin/python" -m pip install --no-index --find-links "$folder/wheels" \
  --constraint "$folder/requirements.lock" --upgrade "$folder"/wheels/splitforge-*.whl
install -d -m 0755 /opt/splitforge-certbot
python3 -m venv /opt/splitforge-certbot
/opt/splitforge-certbot/bin/python -m pip install --no-index --find-links "$folder/wheels" 'certbot>=5.4,<6'
for binary in xray tun2socks slipstream-client dnstt-client noizdns-client; do
  install -m 0755 -- "$folder/bin/$binary" "/usr/local/bin/$binary"
done
install -d -m 0700 /etc/splitforge
ln -sfn -- "$prefix/venv/bin/splitforge" /usr/local/bin/splitforge
if ((restore)); then
  "$prefix/venv/bin/splitforge" restore
fi
"$prefix/venv/bin/splitforge" --version
printf 'Offline installation complete. Run: sudo splitforge\n'
