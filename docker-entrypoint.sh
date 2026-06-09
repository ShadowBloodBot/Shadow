#!/bin/sh
set -e
python scripts/sync_suburbs.py || echo "Suburb sync failed — continuing with existing index if present"
exec python -u bot.py
