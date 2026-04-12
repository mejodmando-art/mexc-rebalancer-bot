#!/bin/bash
# Install the bot as a systemd service on Ubuntu/Debian.
# Run as root: sudo bash deploy/install.sh

set -e

INSTALL_DIR="/opt/mexc-rebalancer-bot"
SERVICE_NAME="mexc-rebalancer"
SERVICE_USER="ubuntu"

echo "=== Installing MEXC Smart Portfolio Bot ==="

# 1. Copy files
mkdir -p "$INSTALL_DIR"
rsync -av --exclude='.git' --exclude='web/node_modules' --exclude='web/.next' \
  "$(dirname "$(dirname "$0")")/" "$INSTALL_DIR/"

# 2. Install Python deps
pip3 install -r "$INSTALL_DIR/requirements.txt"

# 3. Create .env if missing
if [ ! -f "$INSTALL_DIR/.env" ]; then
  cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"
  echo ""
  echo "⚠️  Edit $INSTALL_DIR/.env and add your API keys, then re-run this script."
  exit 0
fi

# 4. Install systemd service
sed "s|/opt/mexc-rebalancer-bot|$INSTALL_DIR|g; s|User=ubuntu|User=$SERVICE_USER|g" \
  "$INSTALL_DIR/deploy/mexc-rebalancer.service" \
  > "/etc/systemd/system/$SERVICE_NAME.service"

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"

echo ""
echo "✅ Service installed and started."
echo "   Status : systemctl status $SERVICE_NAME"
echo "   Logs   : journalctl -u $SERVICE_NAME -f"
echo "   Stop   : systemctl stop $SERVICE_NAME"
