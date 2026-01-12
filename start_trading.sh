#!/bin/bash
# Antigravity Trading Bot - Unified Start Script
# Usage: ./start_trading.sh [--portfolio NAME] [--strategy NAME] [--interval MINS] [--dry-run]

set -e

# Default values
PORTFOLIO="${PORTFOLIO:-my_portfolio}"
STRATEGY="${STRATEGY:-dual_momentum}"
INTERVAL="${INTERVAL:-60}"  # 60 minutes between cycles
MODE="LIVE"
AUTO_CLEAR_HALT="true"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --portfolio)
            PORTFOLIO="$2"
            shift 2
            ;;
        --strategy)
            STRATEGY="$2"
            shift 2
            ;;
        --interval)
            INTERVAL="$2"
            shift 2
            ;;
        --dry-run)
            MODE="LIVE_DRY"
            shift
            ;;
        --no-auto-clear)
            AUTO_CLEAR_HALT="false"
            shift
            ;;
        --help)
            echo "Antigravity Trading Bot"
            echo ""
            echo "Usage: ./start_trading.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --portfolio NAME    Portfolio ID (default: my_portfolio)"
            echo "  --strategy NAME     Strategy name (default: dual_momentum)"
            echo "  --interval MINS     Minutes between cycles (default: 60)"
            echo "  --dry-run           Run in LIVE_DRY mode (no real trades)"
            echo "  --no-auto-clear     Don't auto-clear HALT flags"
            echo "  --help              Show this help"
            echo ""
            echo "Examples:"
            echo "  ./start_trading.sh                          # Start with defaults"
            echo "  ./start_trading.sh --dry-run               # Test mode"
            echo "  ./start_trading.sh --interval 30           # Run every 30 mins"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Change to project directory
cd "$(dirname "$0")"

# Activate virtual environment
source .venv/bin/activate 2>/dev/null || {
    echo -e "${RED}Error: Virtual environment not found. Run: python3 -m venv .venv${NC}"
    exit 1
}

# Log file
LOG_DIR="logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/trading_$(date +%Y%m%d).log"

# Function to log with timestamp
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# Function to clear halt flag
clear_halt() {
    HALT_FILE="data/artifacts/portfolio/${PORTFOLIO}/HALTED"
    if [[ -f "$HALT_FILE" ]]; then
        rm -f "$HALT_FILE"
        log "⚠️  Cleared HALT flag for ${PORTFOLIO}"
    fi
}

# Print startup banner
echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}     🚀 ANTIGRAVITY TRADING BOT - 24/7 AUTONOMOUS${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "Portfolio:  ${BLUE}${PORTFOLIO}${NC}"
echo -e "Strategy:   ${BLUE}${STRATEGY}${NC}"
echo -e "Mode:       ${YELLOW}${MODE}${NC}"
echo -e "Interval:   ${BLUE}${INTERVAL} minutes${NC}"
echo -e "Log File:   ${BLUE}${LOG_FILE}${NC}"
echo ""

if [[ "$MODE" == "LIVE" ]]; then
    echo -e "${RED}⚠️  LIVE MODE - REAL TRADES WILL BE EXECUTED${NC}"
else
    echo -e "${YELLOW}ℹ️  DRY RUN MODE - No real trades${NC}"
fi
echo ""

log "Starting trading bot - Portfolio: ${PORTFOLIO}, Mode: ${MODE}"

# Trap for graceful shutdown
trap 'log "🛑 Received shutdown signal, stopping..."; exit 0' SIGINT SIGTERM

# Main trading loop
CYCLE_COUNT=0
while true; do
    CYCLE_COUNT=$((CYCLE_COUNT + 1))
    
    # Auto-clear halt if enabled
    if [[ "$AUTO_CLEAR_HALT" == "true" ]]; then
        clear_halt
    fi
    
    echo ""
    echo -e "${BLUE}━━━ Cycle #${CYCLE_COUNT} [$(date '+%H:%M:%S')] ━━━${NC}"
    log "Starting cycle #${CYCLE_COUNT}"
    
    # Run single cycle
    python3 scripts/run_live.py \
        --portfolio "$PORTFOLIO" \
        --strategy "$STRATEGY" \
        --mode "$MODE" \
        --max-cycles 1 \
        2>&1 | tee -a "$LOG_FILE"
    
    EXIT_CODE=$?
    
    if [[ $EXIT_CODE -eq 0 ]]; then
        log "✅ Cycle #${CYCLE_COUNT} completed successfully"
    else
        log "❌ Cycle #${CYCLE_COUNT} exited with code ${EXIT_CODE}"
    fi
    
    # Show next run time
    NEXT_RUN=$(date -v+${INTERVAL}M '+%H:%M:%S' 2>/dev/null || date -d "+${INTERVAL} minutes" '+%H:%M:%S')
    echo ""
    echo -e "${GREEN}Next cycle at: ${NEXT_RUN}${NC}"
    echo -e "${YELLOW}Press Ctrl+C to stop${NC}"
    
    # Sleep until next cycle
    sleep $((INTERVAL * 60))
done
