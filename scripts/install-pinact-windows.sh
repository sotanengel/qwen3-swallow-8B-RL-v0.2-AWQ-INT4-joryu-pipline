#!/usr/bin/env bash
# Windows (Git Bash) 向け pinact v4.1.0 インストール。CI と同じバージョン。
set -euo pipefail

bin_dir="${HOME}/.local/bin"
mkdir -p "$bin_dir"
workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT
cd "$workdir"

base="https://github.com/suzuki-shunsuke/pinact/releases/download/v4.1.0"
curl -sSfL -O "${base}/pinact_windows_amd64.zip"
curl -sSfL -O "${base}/pinact_4.1.0_checksums.txt"
sha256sum --ignore-missing -c pinact_4.1.0_checksums.txt
unzip -q pinact_windows_amd64.zip
install -m 755 pinact.exe "${bin_dir}/pinact.exe"
"${bin_dir}/pinact.exe" --version
echo "[install-pinact] installed to ${bin_dir}"
