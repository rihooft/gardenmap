#!/bin/sh
# Lance le serveur GardenMap. Les options de l'add-on sont lues dans /data/options.json par le backend.
set -e
export GARDENMAP_DATA="${GARDENMAP_DATA:-/data}"
export GARDENMAP_STATIC="/app/static"
cd /app
exec python -m uvicorn backend.main:app --host 0.0.0.0 --port 8099 --no-proxy-headers
