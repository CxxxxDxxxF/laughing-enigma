#!/usr/bin/env bash
# ============================================================================
# Antigravity Auto-Run Scheduler
# ============================================================================
# This script runs the trading bot in an infinite loop, automatically
# restarting on crashes. Use with systemd/launchd for true auto-start at boot.
#
# Usage:
#   ./scripts/run_scheduled.sh <portfolio> [strategy] [session] [mode]
#
# Examples:
#   ./scripts/run_scheduled.sh my_portfolio                      # defaults
#   ./scripts/run_scheduled.sh my_portfolio dual_momentum cme_futures LIVE
#
# The bot will:
#   1. Only run during market hours (based on --session)
#   2. Sleep automatically when market is closed
#   3. Restart automatically if it crashes
# ============================================================================

set -e

PORTFOLIO=${1:-"live_portfolio"}
STRATEGY=${2:-"dual_momentum"}
SESSION=${3:-"cme_futures"}
MODE=${4:-"LIVE_DRY"}
INTERVAL=${5:-60}

LOG_FILE="logs/${PORTFOLIO}_$(date +%Y%m%d).log"
mkdir -p logs

echo "================================================================"
echo " ANTIGRAVITY SCHEDULED RUNNER"
echo "================================================================"
echo " Portfolio: $PORTFOLIO"
echo " Strategy:  $STRATEGY"
echo " Session:   $SESSION"
echo " Mode:      $MODE"
echo " Interval:  ${INTERVAL}s"
echo " Log file:  $LOG_FILE"
echo "================================================================"
echo ""
echo "Starting in 3 seconds... Press Ctrl+C to cancel."
sleep 3

RESTART_COUNT=0
MAX_RESTARTS=10

while true; do
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting runner (attempt #$((RESTART_COUNT + 1)))..."
    
    python3 scripts/run_live.py \
        --portfolio "$PORTFOLIO" \
        --strategy "$STRATEGY" \
        --mode "$MODE" \
        --session "$SESSION" \
        --interval "$INTERVAL" \
        ${@:6} \
        --max-cycles 0 2>&1 | tee -a "$LOG_FILE"
    
    EXIT_CODE=$?
    
    if [ $EXIT_CODE -eq 0 ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Runner exited cleanly (code 0). Restarting in 10s..."
        RESTART_COUNT=0
    else
        RESTART_COUNT=$((RESTART_COUNT + 1))
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Runner crashed (code $EXIT_CODE). Restart #$RESTART_COUNT of $MAX_RESTARTS."
        
        if [ $RESTART_COUNT -ge $MAX_RESTARTS ]; then
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] Max restarts reached. Exiting."
            exit 1
        fi
    fi
    
    sleep 10
done
