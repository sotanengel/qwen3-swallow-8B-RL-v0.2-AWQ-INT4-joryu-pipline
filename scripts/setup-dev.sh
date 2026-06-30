#!/usr/bin/env bash
# 開発環境の初期セットアップ。依存インストール + pre-commit フック登録。
#
# 用法:
#   bash scripts/setup-dev.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

log() { echo "[setup-dev] $*" >&2; }

log "uv sync"
uv sync

install_pinact() {
  if command -v pinact >/dev/null 2>&1; then
    log "pinact already installed: $(pinact --version 2>/dev/null || pinact version 2>/dev/null || echo ok)"
    return 0
  fi

  log "pinact not found; installing to ~/.local/bin (CI と同じ v4.1.0)"
  local workdir bin_dir
  workdir="$(mktemp -d)"
  bin_dir="${HOME}/.local/bin"
  mkdir -p "$bin_dir"

  local os arch asset
  os="$(uname -s | tr '[:upper:]' '[:lower:]')"
  arch="$(uname -m)"
  case "$arch" in
    x86_64|amd64) arch="amd64" ;;
    aarch64|arm64) arch="arm64" ;;
    *)
      log "WARN: unsupported arch=$arch; install pinact manually for full pre-commit"
      return 0
      ;;
  esac

  case "$os" in
    linux) asset="pinact_linux_${arch}.tar.gz" ;;
    darwin) asset="pinact_darwin_${arch}.tar.gz" ;;
    mingw*|msys*|cygwin*)
      log "Windows detected; using scripts/install-pinact-windows.sh"
      bash "${ROOT}/scripts/install-pinact-windows.sh"
      export PATH="${HOME}/.local/bin:${PATH}"
      return 0
      ;;
    *)
      log "WARN: unsupported os=$os; install pinact manually for full pre-commit"
      return 0
      ;;
  esac

  local base="https://github.com/suzuki-shunsuke/pinact/releases/download/v4.1.0"
  curl -sSfL -o "${workdir}/${asset}" "${base}/${asset}"
  curl -sSfL -o "${workdir}/pinact_4.1.0_checksums.txt" "${base}/pinact_4.1.0_checksums.txt"
  (
    cd "$workdir"
    sha256sum --ignore-missing -c pinact_4.1.0_checksums.txt 2>/dev/null \
      || shasum -a 256 -c pinact_4.1.0_checksums.txt
    tar -xzf "${asset}" pinact
    install -m 755 pinact "${bin_dir}/pinact"
  )
  rm -rf "$workdir"
  export PATH="${bin_dir}:${PATH}"
  log "pinact installed to ${bin_dir}/pinact"
}

install_pinact

log "pre-commit install (commit hooks only; heavy checks run on GitHub Actions)"
uvx pre-commit install --install-hooks -t pre-commit

log "done. Commit uses pre-commit hooks; push and wait for GitHub Actions (optional locally: bash scripts/check.sh)"
