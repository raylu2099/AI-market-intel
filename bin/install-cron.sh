#!/bin/bash
# Install cron entries for market-intel. Idempotent.
# Works on Synology DSM (/etc/crontab) and standard Linux (user crontab).
#
# Usage: sudo bash install-cron.sh        (Synology, needs root for /etc/crontab)
#        bash install-cron.sh             (standard Linux, user crontab)
set -e

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RUNNER="$PROJECT_DIR/bin/run-slot.sh"
USER="${CRON_USER:-$(whoami)}"
MARKER="# === market-intel slots ==="

# All times in the NAS local timezone (cron runs in system TZ)
CRON_BLOCK="$MARKER
# Deep analysis slots (Claude)
30 18 * * * $USER $RUNNER china_open
0 13 * * 1-5 $USER $RUNNER close
# Light market briefs (Perplexity)
0 6 * * 1-5 $USER $RUNNER premarket
30 6 * * 1-5 $USER $RUNNER open
30 9 * * 1-5 $USER $RUNNER midday
# Per-stock news
30 5 * * 1-5 $USER $RUNNER stocks_pre
30 13 * * 1-5 $USER $RUNNER stocks_post
# Weekly review (Fridays 14:00 PT)
0 14 * * 5 $USER $RUNNER weekly_review"

# Also remove old market-push entries if present
OLD_MARKER_1="# === Market push tasks ==="
OLD_MARKER_2="# === Stock news tasks ==="

install_synology() {
    CRONTAB="/etc/crontab"
    echo "Synology mode: editing $CRONTAB"

    # Remove old market-push entries if present
    for marker in "$OLD_MARKER_1" "$OLD_MARKER_2"; do
        if grep -q "$marker" "$CRONTAB" 2>/dev/null; then
            # Remove from marker line to next blank/marker line
            sed -i "/$marker/,/^$/d" "$CRONTAB"
            echo "  Removed old block: $marker"
        fi
    done

    if grep -q "$MARKER" "$CRONTAB" 2>/dev/null; then
        echo "  market-intel cron already present, skipping."
    else
        printf '\n%s\n' "$CRON_BLOCK" >> "$CRONTAB"
        echo "  Added market-intel cron block."
    fi

    # Reload
    if command -v synoservicectl >/dev/null 2>&1; then
        synoservicectl --reload crond 2>/dev/null || true
    elif command -v systemctl >/dev/null 2>&1; then
        systemctl restart cron 2>/dev/null || true
    fi
    echo "  crond reloaded."
}

install_standard() {
    echo "Standard Linux mode: editing user crontab"
    CURRENT="$(crontab -l 2>/dev/null || true)"
    if echo "$CURRENT" | grep -q "$MARKER"; then
        echo "  market-intel cron already present, skipping."
        return
    fi
    # Strip USER field from entries (user crontab doesn't use it)
    ENTRIES=$(echo "$CRON_BLOCK" | sed "s| $USER | |")
    echo "$CURRENT"$'\n'"$ENTRIES" | crontab -
    echo "  Added market-intel cron entries."
}

chmod +x "$RUNNER"

if [ -f /etc/synoinfo.conf ] || [ -f /etc/crontab ] && [ "$(id -u)" = "0" ]; then
    install_synology
else
    install_standard
fi

echo "Done. Verify with: grep market-intel /etc/crontab  (or crontab -l)"
