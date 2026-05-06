#!/usr/bin/env bash
# Regenerate TypeScript types from the running backend's OpenAPI schema.
#
# Usage:
#   API=http://localhost:8000 ./scripts/gen-types.sh
#
# Requires `openapi-typescript` (run `npm i -D openapi-typescript`).
set -euo pipefail

API=${API:-http://localhost:8000}
OUT=lib/api-types.ts

echo "Fetching $API/openapi.json …"
npx --yes openapi-typescript "$API/openapi.json" -o "$OUT"
echo "Wrote $OUT"
