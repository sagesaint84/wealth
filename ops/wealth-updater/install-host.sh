#!/usr/bin/env bash
# FIRST INSTALL ONLY. Review source, unit, Compose overlay and runbook first.
# This installs the worker, NEVER replaces the running Wealth container.
set -euo pipefail
[[ $(id -u) == 0 ]]
[[ -f app/updater/host.py && -f ops/wealth-updater/wealth-updater.service ]]
[[ ! -e /opt/wealth-updater && ! -e /etc/wealth-updater && ! -e /var/lib/wealth-updater ]]
[[ ! -e /etc/systemd/system/wealth-updater.service && ! -e /etc/tmpfiles.d/wealth-updater.conf ]]
[[ -x /usr/bin/docker && -x /usr/bin/python3 ]]
/usr/bin/python3 -c 'import sys; assert sys.version_info >= (3,10)'
/usr/bin/docker compose version >/dev/null
[[ -f /docker/wealth/docker-compose.ghcr.yml && -f /docker/wealth/docker-compose.override.yml ]]
[[ ! -e /docker/wealth/docker-compose.updater.yml ]]
install -d -m 0700 /opt/wealth-updater/app/updater /etc/wealth-updater/docker /var/lib/wealth-updater /run/wealth-updater
install -m 0600 app/updater/{__init__,protocol,releases,host}.py /opt/wealth-updater/app/updater/
install -m 0600 app/updater/__init__.py /opt/wealth-updater/app/__init__.py
/usr/bin/python3 - <<'PY'
from pathlib import Path
import secrets
p=Path('/etc/wealth-updater/client.key')
p.write_bytes(secrets.token_bytes(32))
p.chmod(0o600)
PY
install -m 0600 ops/wealth-updater/docker-compose.updater.yml /docker/wealth/docker-compose.updater.yml
install -m 0644 ops/wealth-updater/wealth-updater.service /etc/systemd/system/wealth-updater.service
install -m 0644 ops/wealth-updater/wealth-updater.conf /etc/tmpfiles.d/wealth-updater.conf
systemd-tmpfiles --create /etc/tmpfiles.d/wealth-updater.conf
systemctl daemon-reload
systemctl enable --now wealth-updater.service
echo 'Worker installed. Container NOT changed. Follow the reviewed bootstrap runbook with the RELEASED 2.1.4 merge SHA/digest.'
