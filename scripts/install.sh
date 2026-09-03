#!/usr/bin/env bash
# Installs charmera-uploader as a systemd service on an Armbian/Ubuntu-based
# Orange Pi Zero 2W. Run as root (sudo ./scripts/install.sh) from a checkout
# of this repo.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL_DIR=/opt/charmera-uploader

if [[ $EUID -ne 0 ]]; then
  echo "Run this as root (sudo $0)" >&2
  exit 1
fi

echo "==> Installing OS packages"
apt-get update
apt-get install -y python3 python3-venv python3-pip gpiod libgpiod-dev mount util-linux

echo "==> Copying application to $INSTALL_DIR"
mkdir -p "$INSTALL_DIR"
rsync -a --delete --exclude '.git' --exclude '.venv' "$REPO_DIR"/ "$INSTALL_DIR"/

echo "==> Creating virtualenv"
python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip
"$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt"

echo "==> Setting up config/state directories"
mkdir -p /etc/charmera-uploader /var/lib/charmera-uploader
if [[ ! -f /etc/charmera-uploader/config.yaml ]]; then
  cp "$INSTALL_DIR/config.example.yaml" /etc/charmera-uploader/config.yaml
  echo "    Wrote default config to /etc/charmera-uploader/config.yaml - edit it, then re-run."
fi
if [[ ! -f /etc/charmera-uploader/token.json ]]; then
  echo "    NOTE: /etc/charmera-uploader/token.json is missing."
  echo "    Run scripts/setup_google_auth.py on a machine with a browser and copy the result here."
fi

echo "==> Installing systemd service"
cp "$INSTALL_DIR/systemd/charmera-uploader.service" /etc/systemd/system/charmera-uploader.service
systemctl daemon-reload
systemctl enable charmera-uploader.service
systemctl restart charmera-uploader.service || true

echo "==> Done. Check status with: systemctl status charmera-uploader"
