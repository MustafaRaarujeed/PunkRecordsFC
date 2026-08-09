#!/usr/bin/env bash
# Download the historical season data that scripts/backtest.py replays.
#
# Source: github.com/vaastav/Fantasy-Premier-League, which archives per-gameweek
# FPL data going back years. The FPL API itself only exposes season totals for
# past seasons, not the per-gameweek detail a no-lookahead backtest needs.
#
# Writes to data/historical/ (gitignored, ~6MB).

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="$ROOT/data/historical"
BASE="https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/master/data"

mkdir -p "$DEST"

fetch() {
  local src="$1" dst="$2"
  printf '  %-24s' "$dst"
  if curl -sSf --max-time 180 "$BASE/$src" -o "$DEST/$dst"; then
    echo "$(wc -c < "$DEST/$dst" | tr -d ' ') bytes"
  else
    echo "FAILED" >&2
    return 1
  fi
}

echo "fetching historical FPL data -> $DEST"
# 2025-26 is the tuning season; 2024-25 is the holdout. Each needs the season
# before it as the prior for early-season blending, hence 2023-24.
fetch "2025-26/gws/merged_gw.csv" "merged_2025-26.csv"
fetch "2025-26/players_raw.csv"   "raw_2025-26.csv"
fetch "2025-26/teams.csv"         "teams_2025-26.csv"
fetch "2024-25/gws/merged_gw.csv" "merged_2024-25.csv"
fetch "2024-25/players_raw.csv"   "raw_2024-25.csv"
fetch "2024-25/teams.csv"         "teams_2024-25.csv"
fetch "2023-24/players_raw.csv"   "raw_2023-24.csv"

echo
echo "done."
echo "  tuning season: python3 scripts/backtest.py --season 2025-26"
echo "  holdout:       python3 scripts/backtest.py --season 2024-25 --sweep-blend"
