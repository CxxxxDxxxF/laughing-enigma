#!/usr/bin/env bash
# ============================================================================
# Antigravity Dashboard & Launcher
# ============================================================================
# This script starts the scheduled runner in the background and launches
# a real-time terminal dashboard to monitor its progress.
#
# Usage:
#   ./scripts/start_dashboard.sh <portfolio> [strategy] [session] [mode]
#
# Examples:
#   ./scripts/start_dashboard.sh my_portfolio
#   ./scripts/start_dashboard.sh my_portfolio dual_momentum cme_futures LIVE
# ============================================================================

PORTFOLIO=${1:-"live_portfolio"}
STRATEGY=${2:-"dual_momentum"}
SESSION=${3:-"cme_futures"}
MODE=${4:-"LIVE_DRY"}
INTERVAL=${5:-60}

# Create a unique session ID for log separation if needed, 
# but run_scheduled.sh handles day-based logs.
LOG_FILE="logs/${PORTFOLIO}_$(date +%Y%m%d).log"

# Check if a runner is already active for this portfolio?
# For simplicity, we'll just start a new one. User should manage cleanup.

echo "Starting Antigravity Runner in BACKGROUND..."
nohup ./scripts/run_scheduled.sh "$PORTFOLIO" "$STRATEGY" "$SESSION" "$MODE" "$INTERVAL" --optimize-off-hours > /dev/null 2>&1 &
RUNNER_PID=$!

echo "Runner PID: $RUNNER_PID"
echo "Logs: $LOG_FILE"
echo "Press Ctrl+C to stop monitoring (Runner will keep running)."
sleep 2

# Monitoring Loop
while kill -0 $RUNNER_PID 2>/dev/null; do
    clear
    echo "================================================================"
    echo " ANTIGRAVITY LIVE DASHBOARD"
    echo "================================================================"
    echo " Runner PID: $RUNNER_PID | Mode: $MODE | Session: $SESSION"
    echo " Log File: $LOG_FILE"
    echo "================================================================"
    
    # 1. Market Status
    python3 scripts/dashboard.py --portfolio "$PORTFOLIO" market | head -n 6 | tail -n +2
    echo ""
    
    # 2. Portfolio Status
    python3 scripts/dashboard.py --portfolio "$PORTFOLIO" status | grep -v -- "---"
    echo ""
    
    # 3. Positions
    echo "--- Open Positions ---"
    python3 scripts/dashboard.py --portfolio "$PORTFOLIO" positions | tail -n +3
    echo ""
    
    # 4. Recent Logs (Last 10 lines)
    echo "================================================================"
    echo " RECENT LOGS"
    echo "================================================================"
    if [ -f "$LOG_FILE" ]; then
        tail -n 10 "$LOG_FILE"
    else
        echo "Waiting for log file..."
    fi
    
    sleep 5
done

echo "Runner exited."
