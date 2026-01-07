#!/usr/bin/env bash
# Usage: ./scripts/run_and_monitor.sh <portfolio_id> [strategy_id] [interval]

PORTFOLIO=${1:-"live_portfolio"}
STRATEGY=${2:-"dual_momentum"}
INTERVAL=${3:-5}

# Kill child processes on exit
trap "kill 0" EXIT

echo "----------------------------------------------------------------"
echo "Starting Antigravity Trading System"
echo "Portfolio: $PORTFOLIO"
echo "Strategy:  $STRATEGY"
echo "Interval:  $INTERVAL seconds"
echo "----------------------------------------------------------------"

# 1. Start the Runner in the background
# We redirect stderr to stdout to capture everything in the log
python3 scripts/run_live.py \
    --portfolio "$PORTFOLIO" \
    --strategy "$STRATEGY" \
    --mode LIVE_DRY \
    --max-cycles 0 \
    --interval "$INTERVAL" > run.log 2>&1 &

RUNNER_PID=$!
echo "[*] Runner started (PID $RUNNER_PID). Logs: run.log"
sleep 2  # Give it a moment to initialize

# 2. Monitor Loop
while kill -0 $RUNNER_PID 2>/dev/null; do
    clear
    echo "================================================================"
    echo " ANTIGRAVITY LIVE MONITOR | $(date '+%Y-%m-%d %H:%M:%S')"
    echo "================================================================"
    
    # 2a. Status
    python3 scripts/dashboard.py --portfolio "$PORTFOLIO" status
    echo ""
    
    # 2b. Metrics
    python3 scripts/dashboard.py --portfolio "$PORTFOLIO" metrics
    echo ""
    
    # 2c. Positions
    python3 scripts/dashboard.py --portfolio "$PORTFOLIO" positions
    
    echo "================================================================"
    echo " Runner (PID $RUNNER_PID) is active. Press Ctrl+C to stop."
    echo " Tailing last 3 log lines:"
    tail -n 3 run.log
    
    sleep 5
done

echo ""
echo "[!] Runner stopped."
