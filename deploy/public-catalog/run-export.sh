#!/usr/bin/env bash
# Read only the shared catalog, then atomically publish public static snapshots.
set -euo pipefail

PUBLIC_CATALOG_ROOT="${PUBLIC_CATALOG_ROOT:-/opt/opencareer-public-feed}"
PUBLIC_CATALOG_OUTPUT="${PUBLIC_CATALOG_OUTPUT:-/opt/opencareer/deploy/web/public/jobs/v1}"
PUBLIC_CATALOG_CONTAINER="${PUBLIC_CATALOG_CONTAINER:-opencareer-alpha-backend-a-1}"

test -f "$PUBLIC_CATALOG_ROOT/public_catalog_export.py"
test -f "$PUBLIC_CATALOG_ROOT/public_catalog_format.py"
test -f "$PUBLIC_CATALOG_ROOT/sources.txt"
test -d "$PUBLIC_CATALOG_OUTPUT"
exec 9>"$PUBLIC_CATALOG_ROOT/export.lock"
flock -n 9 || exit 0
test "$(docker inspect --format '{{.State.Running}}' "$PUBLIC_CATALOG_CONTAINER")" = true

catalog_source_slugs="$(tr -d '\n\r' < "$PUBLIC_CATALOG_ROOT/sources.txt")"
docker exec -i "$PUBLIC_CATALOG_CONTAINER" python - --slugs "$catalog_source_slugs" \
  < "$PUBLIC_CATALOG_ROOT/public_catalog_export.py" \
  | python3 "$PUBLIC_CATALOG_ROOT/public_catalog_format.py" --output "$PUBLIC_CATALOG_OUTPUT"
