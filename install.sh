#!/usr/bin/env bash
set -Eeuo pipefail
umask 022

prefix=/opt/splitforge
cores=1
upgrade=0
restore=0
while (($#)); do
  case "$1" in
    --prefix) prefix=${2:?--prefix requires an absolute directory}; shift 2 ;;
    --skip-proxy-cores) cores=0; shift ;;
    --upgrade) upgrade=1; shift ;;
    --restore) restore=1; shift ;;
    -h|--help)
      printf '%s\n' 'Usage: sudo bash install.sh [--prefix /opt/splitforge] [--skip-proxy-cores] [--upgrade] [--restore]'
      exit 0 ;;
    *) printf 'Unknown option: %s\n' "$1" >&2; exit 2 ;;
  esac
done
[[ $EUID -eq 0 ]] || { printf 'Run this installer with sudo/root.\n' >&2; exit 1; }
[[ $(uname -s) == Linux && -d /run/systemd/system ]] || { printf 'Linux with systemd is required.\n' >&2; exit 1; }
[[ $prefix == /* && $prefix != / && $prefix != *$'\n'* ]] || { printf 'Invalid installation prefix.\n' >&2; exit 2; }
source /etc/os-release
[[ ${ID:-} == ubuntu || ${ID:-} == debian || " ${ID_LIKE:-} " == *' debian '* ]] || {
  printf 'This installer supports Ubuntu/Debian.\n' >&2; exit 1;
}
source_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
[[ -f $source_dir/pyproject.toml ]] || { printf 'Run from a complete SplitForge checkout.\n' >&2; exit 1; }
if [[ -x $prefix/venv/bin/splitforge ]]; then
  ((upgrade)) || { printf 'Existing installation: use --upgrade.\n' >&2; exit 1; }
  "$prefix/venv/bin/splitforge" stop-all --preserve
fi
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends git python3 python3-venv ca-certificates iproute2 nftables procps wireguard-tools openvpn proxychains4
python3 -c 'import sys; assert sys.version_info >= (3, 10), "Python 3.10+ is required"'
install -d -m 0755 -- "$prefix"
python3 -m venv "$prefix/venv"
"$prefix/venv/bin/python" -m pip install --constraint "$source_dir/requirements.lock" --upgrade "$source_dir"
install -d -m 0700 /etc/splitforge
ln -sfn -- "$prefix/venv/bin/splitforge" /usr/local/bin/splitforge
if ((cores)); then
  "$prefix/venv/bin/splitforge" dependencies install xray
  "$prefix/venv/bin/splitforge" dependencies install tun2socks
fi
"$prefix/venv/bin/splitforge" doctor
if ((restore)); then
  "$prefix/venv/bin/splitforge" restore
fi
if revision=$(git -C "$source_dir" rev-parse --verify HEAD 2>/dev/null); then
  printf '%s\n' "$revision" > "$prefix/.splitforge-revision"
  chmod 0644 "$prefix/.splitforge-revision"
fi
printf '\nSplitForge installed. Run: sudo splitforge\nRead-only preview: splitforge --demo\n'
