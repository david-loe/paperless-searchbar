#!/bin/sh
set -eu
umask 077
alembic upgrade head
# Exactly one worker: SQLite and login throttling are designed for a single app instance.
exec uvicorn searchbar.app:create_app --factory --host 0.0.0.0 --port 8000 --workers 1 \
  --proxy-headers --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-127.0.0.1}" --no-access-log
