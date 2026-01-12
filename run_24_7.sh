#!/bin/bash
# Antigravity Trading System - Complete Automation Script
# 
# This script runs the bot during market hours AND optimization during off-hours.
#
# Usage:
#   ./run_24_7.sh                    # Run full automation
#   ./run_24_7.sh --optimize-only    # Run optimization only
#   ./run_24_7.sh --trade-only       # Run trading only

set -e

# Default settings
PORTFOLIO="${PORTFOLIO:-my_portfolio}"
STRATEGY="${STRATEGY:-dual_momentum}"
TICKERS="SPY QQQ IWM"
MODE="LIVE"
TRADE_INTERVAL=60  # minutes

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Parse arguments
OPTIMIZE_ONLY=false
TRADE_ONLY=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --optimize-only) OPTIMIZE_ONLY=true; shift ;;
        --trade-only) TRADE_ONLY=true; shift ;;
        --dry-run) MODE="LIVE_DRY"; shift ;;
        --help)
            echo "Antigravity 24/7 Trading System"
            echo ""
            echo "Usage: ./run_24_7.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --optimize-only   Only run optimization (no trading)"
            echo "  --trade-only      Only run trading (no optimization)"
            echo "  --dry-run         Run in paper trading mode"
            echo "  --help            Show this help"
            exit 0
            ;;
        *) shift ;;
    esac
done

cd "$(dirname "$0")"
source .venv/bin/activate 2>/dev/null || { echo "❌ Run: python3 -m venv .venv"; exit 1; }

# Log file
LOG_DIR="logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/trading_$(date +%Y%m%d).log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

is_market_open() {
    # US Equities: 9:30 AM - 4:00 PM ET, Monday-Friday
    python3 -c "
from datetime import datetime
import zoneinfo

tz = zoneinfo.ZoneInfo('America/New_York')
now = datetime.now(tz)
weekday = now.weekday()
hour = now.hour
minute = now.minute
time_minutes = hour * 60 + minute

# Market hours: 9:30 AM (570) to 4:00 PM (960)
is_weekday = weekday < 5
is_market_time = 570 <= time_minutes < 960

if is_weekday and is_market_time:
    exit(0)  # Market open
else:
    exit(1)  # Market closed
" 2>/dev/null
    return $?
}

run_optimization() {
    echo ""
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}  🌙 RUNNING OVERNIGHT OPTIMIZATION${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo ""
    
    log "Starting overnight optimization for: $TICKERS"
    
    python3 scripts/overnight_optimize.py --tickers $TICKERS 2>&1 | tee -a "$LOG_FILE"
    
    if [[ $? -eq 0 ]]; then
        log "✅ Optimization completed successfully"
    else
        log "⚠️ Optimization had issues"
    fi
}

run_trading_cycle() {
    log "Running trading cycle..."
    
    # Clear any halt flags
    rm -f "data/artifacts/portfolio/${PORTFOLIO}/HALTED" 2>/dev/null
    
    python3 scripts/run_live.py \
        --portfolio "$PORTFOLIO" \
        --strategy "$STRATEGY" \
        --mode "$MODE" \
        --session us_equities \
        --max-cycles 1 \
        2>&1 | tee -a "$LOG_FILE"
}

# Main banner
echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  🚀 ANTIGRAVITY 24/7 TRADING SYSTEM${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "Portfolio:  ${BLUE}${PORTFOLIO}${NC}"
echo -e "Strategy:   ${BLUE}${STRATEGY}${NC}"
echo -e "Tickers:    ${BLUE}${TICKERS}${NC}"
echo -e "Mode:       ${YELLOW}${MODE}${NC}"
echo -e "Log File:   ${BLUE}${LOG_FILE}${NC}"
echo ""

log "Starting 24/7 trading system"

# Trap for graceful shutdown
trap 'log "🛑 Shutdown signal received"; exit 0' SIGINT SIGTERM

# Main loop
while true; do
    if is_market_open; then
        # MARKET HOURS: Run trading
        echo ""
        echo -e "${GREEN}✅ Market OPEN - Running trading cycle${NC}"
        
        if [[ "$OPTIMIZE_ONLY" != "true" ]]; then
            run_trading_cycle
        else
            log "Skipping trading (--optimize-only mode)"
        fi
        
        echo -e "${YELLOW}⏰ Next cycle in ${TRADE_INTERVAL} minutes${NC}"
        sleep $((TRADE_INTERVAL * 60))
        
    else
        # OFF HOURS: Run optimization
        echo ""
        echo -e "${BLUE}🌙 Market CLOSED - Off-hours mode${NC}"
        
        if [[ "$TRADE_ONLY" != "true" ]]; then
            # Only run optimization once per night (check if already ran today)
            OPT_FLAG="data/.optimization_ran_$(date +%Y%m%d)"
            
            if [[ ! -f "$OPT_FLAG" ]]; then
                run_optimization
                touch "$OPT_FLAG"
            else
                log "Optimization already ran today, skipping"
            fi
        fi
        
        # Calculate time until market opens
        WAIT_MINS=$(python3 -c "
from datetime import datetime, timedelta
import zoneinfo

tz = zoneinfo.ZoneInfo('America/New_York')
now = datetime.now(tz)

# Next market open
if now.weekday() >= 5:  # Weekend
    days_until_monday = 7 - now.weekday()
    next_open = (now + timedelta(days=days_until_monday)).replace(hour=9, minute=30, second=0)
elif now.hour >= 16:  # After market close
    next_open = (now + timedelta(days=1)).replace(hour=9, minute=30, second=0)
    if next_open.weekday() >= 5:
        next_open += timedelta(days=7 - next_open.weekday())
else:  # Before market open
    next_open = now.replace(hour=9, minute=30, second=0)

delta = next_open - now
print(int(delta.total_seconds() / 60))
" 2>/dev/null)
        
        if [[ -n "$WAIT_MINS" && "$WAIT_MINS" -gt 0 ]]; then
            HOURS=$((WAIT_MINS / 60))
            MINS=$((WAIT_MINS % 60))
            echo -e "${YELLOW}⏰ Market opens in ${HOURS}h ${MINS}m. Sleeping...${NC}"
            
            # Sleep in shorter intervals (check every 15 mins) to be responsive
            SLEEP_MINS=$((WAIT_MINS > 15 ? 15 : WAIT_MINS))
            sleep $((SLEEP_MINS * 60))
        else
            # Fallback: sleep 15 minutes
            sleep 900
        fi
    fi
done
