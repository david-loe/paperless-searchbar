#!/usr/bin/env bash
set -euo pipefail
image="${1:-searchbar:test}"
container="searchbar-smoke-${RANDOM}-$$"
volume="${container}-data"
cleanup() { docker rm -f "$container" >/dev/null 2>&1 || true; docker volume rm "$volume" >/dev/null 2>&1 || true; }
trap cleanup EXIT
docker volume create "$volume" >/dev/null
docker run -d --name "$container" --read-only --tmpfs /tmp --cap-drop ALL \
  --security-opt no-new-privileges:true -p 127.0.0.1::8000 \
  -e SECRET_KEY=smoke-test-only-secret-key-at-least-32-characters \
  -e PAPERLESS_TOKEN=smoke-test -e PAPERLESS_URL=http://paperless.invalid \
  -e PAPERLESS_PUBLIC_URL=https://paperless.invalid \
  --mount "type=volume,source=$volume,target=/data" "$image" >/dev/null
port="$(docker inspect --format '{{(index (index .NetworkSettings.Ports "8000/tcp") 0).HostPort}}' "$container")"
wait_healthy() {
  for attempt in $(seq 1 40); do
    if curl --silent --fail --max-time 2 "http://127.0.0.1:$port/health" >/dev/null; then return; fi
    if [ "$(docker inspect --format '{{.State.Running}}' "$container")" != true ]; then
      docker logs "$container"
      return 1
    fi
    sleep 1
  done
  docker logs "$container"
  return 1
}
wait_healthy
curl --silent --fail --max-time 2 "http://127.0.0.1:$port/" | python3 -c 'import sys; assert "<html lang=\"de\">" in sys.stdin.read()'
docker exec "$container" python -c 'import os; assert os.getuid() == 10001; from searchbar.db import database, Profile; from searchbar.config import get_settings; _, factory = database(get_settings().database_url); db = factory(); db.add(Profile(name="Persistenztest", rules={})); db.commit()'
# Exercise the non-interactive admin bootstrap inside the non-root runtime image.
admin_code="$(docker exec "$container" python -m searchbar.cli admin-code | sed -n '2p')"
printf '%s' "$admin_code" | docker exec -i "$container" python -c 'import sys; from searchbar.db import database, User; from searchbar.config import get_settings; from searchbar.security import digest; from sqlalchemy import select; settings = get_settings(); _, factory = database(settings.database_url); db = factory(); code = sys.stdin.read(); user = db.scalar(select(User).where(User.username == "admin")); assert len(code) >= 32 and user.is_admin and user.local_code_digest == digest(settings, code)'
docker restart "$container" >/dev/null
# Docker may allocate a different ephemeral host port after a restart.
port="$(docker inspect --format '{{(index (index .NetworkSettings.Ports "8000/tcp") 0).HostPort}}' "$container")"
wait_healthy
docker exec "$container" python -c 'from searchbar.db import database, Profile; from searchbar.config import get_settings; from sqlalchemy import select; _, factory = database(get_settings().database_url); db = factory(); assert db.scalar(select(Profile)).name == "Persistenztest"'
echo 'Container smoke test passed: HTTP, migrations, non-root, admin-code CLI and volume persistence.'
