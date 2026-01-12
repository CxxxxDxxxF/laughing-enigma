#!/bin/bash
# ============================================================
# Terminal Setup Script - Antigravity Trading System
# ============================================================
# Installs:
# - Oh My Zsh (if not present)
# - Powerlevel10k theme
# - zsh-syntax-highlighting
# - zsh-autosuggestions
# - Trading aliases
# ============================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo ""
echo -e "${CYAN}===========================================================${NC}"
echo -e "${CYAN}  [*] ANTIGRAVITY TERMINAL SETUP${NC}"
echo -e "${CYAN}===========================================================${NC}"
echo ""

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# ============================================================
# 1. Check for Zsh
# ============================================================
echo -e "${YELLOW}[1/6]${NC} Checking Zsh..."

if ! command -v zsh &> /dev/null; then
    echo -e "${RED}Zsh not found. Installing...${NC}"
    if [[ "$OSTYPE" == "darwin"* ]]; then
        brew install zsh
    else
        sudo apt-get install -y zsh
    fi
fi

echo -e "${GREEN}[OK] Zsh installed${NC}"

# ============================================================
# 2. Install Oh My Zsh
# ============================================================
echo -e "${YELLOW}[2/6]${NC} Installing Oh My Zsh..."

if [ ! -d "$HOME/.oh-my-zsh" ]; then
    sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)" "" --unattended
    echo -e "${GREEN}[OK] Oh My Zsh installed${NC}"
else
    echo -e "${GREEN}[OK] Oh My Zsh already installed${NC}"
fi

ZSH_CUSTOM="${ZSH_CUSTOM:-$HOME/.oh-my-zsh/custom}"

# ============================================================
# 3. Install Powerlevel10k
# ============================================================
echo -e "${YELLOW}[3/6]${NC} Installing Powerlevel10k..."

if [ ! -d "$ZSH_CUSTOM/themes/powerlevel10k" ]; then
    git clone --depth=1 https://github.com/romkatv/powerlevel10k.git "$ZSH_CUSTOM/themes/powerlevel10k"
    echo -e "${GREEN}[OK] Powerlevel10k installed${NC}"
else
    echo -e "${GREEN}[OK] Powerlevel10k already installed${NC}"
fi

# ============================================================
# 4. Install Plugins
# ============================================================
echo -e "${YELLOW}[4/6]${NC} Installing plugins..."

# Syntax highlighting
if [ ! -d "$ZSH_CUSTOM/plugins/zsh-syntax-highlighting" ]; then
    git clone https://github.com/zsh-users/zsh-syntax-highlighting.git "$ZSH_CUSTOM/plugins/zsh-syntax-highlighting"
    echo -e "${GREEN}[OK] zsh-syntax-highlighting installed${NC}"
else
    echo -e "${GREEN}[OK] zsh-syntax-highlighting already installed${NC}"
fi

# Auto-suggestions
if [ ! -d "$ZSH_CUSTOM/plugins/zsh-autosuggestions" ]; then
    git clone https://github.com/zsh-users/zsh-autosuggestions "$ZSH_CUSTOM/plugins/zsh-autosuggestions"
    echo -e "${GREEN}[OK] zsh-autosuggestions installed${NC}"
else
    echo -e "${GREEN}[OK] zsh-autosuggestions already installed${NC}"
fi

# ============================================================
# 5. Configure .zshrc
# ============================================================
echo -e "${YELLOW}[5/6]${NC} Configuring .zshrc..."

ZSHRC="$HOME/.zshrc"

# Backup existing .zshrc
if [ -f "$ZSHRC" ]; then
    cp "$ZSHRC" "$ZSHRC.backup.$(date +%Y%m%d_%H%M%S)"
    echo -e "${GREEN}[OK] Backed up existing .zshrc${NC}"
fi

# Update theme
if grep -q 'ZSH_THEME=' "$ZSHRC"; then
    sed -i.bak 's/ZSH_THEME=".*"/ZSH_THEME="powerlevel10k\/powerlevel10k"/' "$ZSHRC"
else
    echo 'ZSH_THEME="powerlevel10k/powerlevel10k"' >> "$ZSHRC"
fi

# Update plugins
if grep -q 'plugins=(' "$ZSHRC"; then
    # Check if plugins already include our additions
    if ! grep -q 'zsh-syntax-highlighting' "$ZSHRC"; then
        sed -i.bak 's/plugins=(\(.*\))/plugins=(\1 zsh-syntax-highlighting zsh-autosuggestions)/' "$ZSHRC"
    fi
else
    echo 'plugins=(git zsh-syntax-highlighting zsh-autosuggestions)' >> "$ZSHRC"
fi

echo -e "${GREEN}[OK] Updated theme and plugins${NC}"

# ============================================================
# 6. Add Trading Aliases
# ============================================================
echo -e "${YELLOW}[6/6]${NC} Adding trading aliases..."

# Check if aliases already exist
if ! grep -q '# Antigravity Trading Aliases' "$ZSHRC"; then
    cat >> "$ZSHRC" << EOF

# ============================================================
# Antigravity Trading Aliases
# ============================================================
alias trade='cd $SCRIPT_DIR && ./run_24_7.sh'
alias dash='cd $SCRIPT_DIR && python3 scripts/algo_command_center.py'
alias backtest='cd $SCRIPT_DIR && python3 scripts/quick_backtest.py --years 5'
alias core='cd $SCRIPT_DIR && python3 scripts/core_explore.py'
alias trades='cd $SCRIPT_DIR && python3 scripts/dashboard.py --portfolio my_portfolio trades'
alias watch='cd $SCRIPT_DIR && python3 scripts/dashboard.py --portfolio my_portfolio watch'
alias optimize='cd $SCRIPT_DIR && python3 scripts/overnight_optimize.py'
alias status='cd $SCRIPT_DIR && python3 scripts/dashboard.py --portfolio my_portfolio status'

# Quick navigation
alias ag='cd $SCRIPT_DIR'

# Python virtual environment
alias venv='source $SCRIPT_DIR/.venv/bin/activate'
EOF
    echo -e "${GREEN}[OK] Trading aliases added${NC}"
else
    echo -e "${GREEN}[OK] Trading aliases already exist${NC}"
fi

# ============================================================
# Done!
# ============================================================
echo ""
echo -e "${CYAN}===========================================================${NC}"
echo -e "${GREEN}  [OK] SETUP COMPLETE!${NC}"
echo -e "${CYAN}===========================================================${NC}"
echo ""
echo -e "  ${YELLOW}Next steps:${NC}"
echo -e "  1. Restart your terminal OR run: ${CYAN}source ~/.zshrc${NC}"
echo -e "  2. Run: ${CYAN}p10k configure${NC} to customize Powerlevel10k"
echo -e ""
echo -e "  ${YELLOW}New commands available:${NC}"
echo -e "  ${CYAN}trade${NC}     - Start 24/7 trading"
echo -e "  ${CYAN}dash${NC}      - Launch Algo Command Center"
echo -e "  ${CYAN}backtest${NC}  - Run 5-year backtest"
echo -e "  ${CYAN}core${NC}      - Start Core & Explore strategy"
echo -e "  ${CYAN}trades${NC}    - Show recent trades"
echo -e "  ${CYAN}watch${NC}     - Live monitoring dashboard"
echo -e "  ${CYAN}optimize${NC}  - Run overnight optimization"
echo -e "  ${CYAN}ag${NC}        - Navigate to project folder"
echo -e "  ${CYAN}venv${NC}      - Activate Python virtual environment"
echo ""
echo -e "${CYAN}===========================================================${NC}"
