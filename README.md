# Antigravity Trading System

A fully autonomous algorithmic trading system for stocks, with strategy optimization, risk management, and 24/7 operation.

## 🚀 Quick Start

```bash
# 1. Set up environment
python3 -m venv .venv
source .venv/bin/activate
pip install numpy pandas python-dotenv alpaca-py

# 2. Configure Alpaca credentials
cp .env.example .env
# Edit .env with your Alpaca API keys

# 3. Start 24/7 autonomous trading
./run_24_7.sh
```

## 📊 Commands

| Command | Description |
|---------|-------------|
| `./run_24_7.sh` | Full 24/7 automation (trade + optimize) |
| `./start_trading.sh` | Simple trading loop |
| `./start_trading.sh --dry-run` | Paper trading mode |
| `python3 scripts/dashboard.py --portfolio my_portfolio watch` | Live monitoring |
| `python3 scripts/overnight_optimize.py` | Run strategy optimization |
| `python3 scripts/quick_backtest.py --years 5` | Backtest strategy |

## 📁 Project Structure

```
├── scripts/                 # Executable scripts
│   ├── run_live.py         # Main trading runner
│   ├── dashboard.py        # CLI dashboard
│   ├── overnight_optimize.py # Strategy optimization
│   └── quick_backtest.py   # Fast backtesting
├── src/                    # Core source code
│   ├── core/              # Config, metrics, logging
│   ├── execution/         # Order execution engines
│   ├── lifecycle/         # Trading cycle runner
│   ├── strategy/          # Trading strategies
│   ├── rebalance/         # Portfolio rebalancing
│   └── allocation/        # Position sizing
├── docs/                  # Documentation
│   ├── audits/           # System audits
│   └── contracts/        # Design contracts
├── configs/              # Strategy configurations
├── tests/                # Unit tests
└── data/                 # Artifacts and state
```

## 🎯 Current Strategy

**Dual Momentum** on SPY, QQQ, IWM:
- Lookback: 189 days
- Threshold: 10% minimum momentum
- Logic: Buy indices with 6-month return > 10%

## 📈 Backtest Results (5 years)

| Metric | Value |
|--------|-------|
| Annual Return | +12.7% |
| Sharpe Ratio | 1.04 |
| Max Drawdown | -13.4% |
| Total Profit | $65,746 (on $100K) |

## 🔧 Dashboard Commands

```bash
# Real-time monitoring
python3 scripts/dashboard.py --portfolio my_portfolio watch

# Check recent trades
python3 scripts/dashboard.py --portfolio my_portfolio trades

# Sync with broker
python3 scripts/dashboard.py --portfolio my_portfolio sync

# Clear halt flag
python3 scripts/dashboard.py --portfolio my_portfolio clear-halt
```

## ⚙️ Configuration

Edit `scripts/run_live.py` to change:
- Tickers to trade
- Strategy parameters
- Risk limits
- Trading session (market hours)

## 📝 License

Private - All rights reserved.
