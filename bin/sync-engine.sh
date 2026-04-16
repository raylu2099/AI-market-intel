#!/bin/bash
# C2: Sync engine changes from CLI repo to App repo.
# Run from market-intel/ (CLI source of truth).
#
# Usage: ./bin/sync-engine.sh [--dry-run]

set -e

CLI_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_DIR="${APP_DIR:-${CLI_DIR}-app}"
DRY="${1:-}"

if [ ! -d "$APP_DIR" ]; then
    echo "❌ App repo not found at $APP_DIR"
    echo "   Set APP_DIR env var or place repos as siblings:"
    echo "   market-intel/  market-intel-app/"
    exit 1
fi

echo "Syncing from: $CLI_DIR"
echo "            → $APP_DIR"
echo ""

sync() {
    local src="$1"
    local dst="$2"
    if [ "$DRY" = "--dry-run" ]; then
        diff -rq "$src" "$dst" 2>/dev/null | head -20 || true
    else
        cp -r "$src" "$dst"
        echo "  synced: $(basename "$src")"
    fi
}

# Sync core engine modules (intel/ and prompts/)
for dir in "intel" "prompts" "tests"; do
    if [ -d "$CLI_DIR/$dir" ]; then
        rm -rf "$APP_DIR/$dir" 2>/dev/null
        cp -r "$CLI_DIR/$dir" "$APP_DIR/$dir"
        echo "✓ $dir/"
    fi
done

# Sync bin scripts (except sync-engine.sh itself)
for f in "$CLI_DIR"/bin/*.sh "$CLI_DIR"/bin/*.py; do
    [ -f "$f" ] || continue
    name=$(basename "$f")
    [ "$name" = "sync-engine.sh" ] && continue
    cp "$f" "$APP_DIR/bin/$name"
done
echo "✓ bin/ (scripts)"

# Sync .env.example and requirements (but app has its own additions)
cp "$CLI_DIR/.env.example" "$APP_DIR/.env.example"
echo "✓ .env.example"

echo ""
echo "Done. Review changes in $APP_DIR with git diff before committing."
