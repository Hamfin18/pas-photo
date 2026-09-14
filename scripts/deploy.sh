#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/var/www/pas-photo"
cd "$APP_DIR"

git fetch origin main
git checkout main
git reset --hard origin/main

"${APP_DIR}/.venv/bin/pip" install -r requirements.txt -q

systemctl restart pas-photo.service
systemctl is-active --quiet pas-photo.service

echo "Deploy OK: $(git rev-parse --short HEAD)"
