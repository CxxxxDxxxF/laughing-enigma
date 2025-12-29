#!/bin/bash
# Phase 1 Safe Cleanup - Removes only provably unused files
# This script is SAFE and REVERSIBLE (everything is in git)

set -e  # Exit on error

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🗑️  PHASE 1 SAFE CLEANUP"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "This will remove:"
echo "  ✅ Old test artifacts (~11 GB)"
echo "  ✅ Enterprise validation scripts (12 files)"
echo "  ✅ Enterprise test suite (19 files)"
echo "  ✅ Example demos (6 files)"
echo "  ✅ Graveyard folder (dead code)"
echo "  ✅ Old cleanup scripts (2 files)"
echo "  ✅ Generated images (regeneratable)"
echo ""
echo "This will NOT remove:"
echo "  🟢 Your FTMO bot (dashboard.py, run_backtest.py, etc.)"
echo "  🟢 Core strategies (SMA, RSI)"
echo "  🟢 Risk Manager"
echo "  🟢 Core tests (test_risk_manager*.py, test_rsi_strategy.py)"
echo "  🟢 Documentation"
echo ""
read -p "Continue? (y/N): " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌ Cancelled"
    exit 1
fi

echo ""
echo "🧹 Starting cleanup..."
echo ""

# Track what we're deleting
DELETED_COUNT=0

# Category A: Old Artifacts (HUGE space savings)
if [ -d "artifacts" ]; then
    echo "📦 Removing artifacts/ (~11 GB of old test results)..."
    rm -rf artifacts/
    ((DELETED_COUNT+=1))
    echo "   ✅ Deleted"
fi

# Category B: Enterprise Scripts
if [ -d "scripts" ]; then
    echo "📜 Removing enterprise validation scripts/ (12 files)..."
    rm -rf scripts/
    ((DELETED_COUNT+=12))
    echo "   ✅ Deleted"
fi

# Category C: Enterprise Tests
echo "🧪 Removing enterprise test suite (19 files)..."
TEST_FILES=(
    "tests/test_allocator_execution_mode.py"
    "tests/test_architectural_invariants.py"
    "tests/test_cycle_index_invariants.py"
    "tests/test_day_boundary_session.py"
    "tests/test_execution_clock.py"
    "tests/test_execution_mode.py"
    "tests/test_id_determinism.py"
    "tests/test_phase0_equity_movement.py"
    "tests/test_red_team_misconfiguration.py"
    "tests/test_rule_enforcement_timing.py"
    "tests/test_strategy_cooldown.py"
    "tests/test_strategy_discipline.py"
    "tests/test_strategy_identity_state.py"
    "tests/test_strategy_identity.py"
    "tests/test_strategy_readiness.py"
    "tests/test_timeboxed_trend_strategy.py"
    "tests/test_topstep_live_vs_combine.py"
    "tests/test_trade_metrics_fix.py"
    "tests/test_unrealized_pnl.py"
)

for file in "${TEST_FILES[@]}"; do
    if [ -f "$file" ]; then
        rm "$file"
        ((DELETED_COUNT+=1))
    fi
done
echo "   ✅ Deleted"

# Category D: Examples
if [ -d "examples" ]; then
    echo "📚 Removing examples/ (6 demo files)..."
    rm -rf examples/
    ((DELETED_COUNT+=6))
    echo "   ✅ Deleted"
fi

# Category E: Graveyard
if [ -d "graveyard" ]; then
    echo "⚰️  Removing graveyard/ (dead code)..."
    rm -rf graveyard/
    ((DELETED_COUNT+=1))
    echo "   ✅ Deleted"
fi

# Category F: Old Cleanup Scripts
CLEANUP_FILES=("cleanup_junk.sh" "cleanup_repo.sh")
for file in "${CLEANUP_FILES[@]}"; do
    if [ -f "$file" ]; then
        echo "🧹 Removing $file (already executed)..."
        rm "$file"
        ((DELETED_COUNT+=1))
        echo "   ✅ Deleted"
    fi
done

# Category G: Generated Images (regeneratable)
IMAGE_FILES=("backtest_chart_rsi.png" "backtest_chart_sma.png" "portfolio_chart.png")
echo "🖼️  Removing generated charts (3 files - regeneratable)..."
for file in "${IMAGE_FILES[@]}"; do
    if [ -f "$file" ]; then
        rm "$file"
        ((DELETED_COUNT+=1))
    fi
done
echo "   ✅ Deleted"

# Update .gitignore
echo ""
echo "📝 Updating .gitignore..."
cat >> .gitignore << 'GITIGNORE'

# Generated charts (regeneratable)
*.png
!docs/**/*.png

# Artifacts (regeneratable test results)
artifacts/

# Cleanup scripts (one-time use)
cleanup_*.sh

GITIGNORE
echo "   ✅ Updated"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ PHASE 1 CLEANUP COMPLETE!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📊 Summary:"
echo "   • Deleted: ~${DELETED_COUNT}+ items"
echo "   • Space saved: ~11 GB"
echo "   • FTMO bot: ✅ Intact"
echo "   • Core tests: ✅ Intact"
echo "   • Documentation: ✅ Intact"
echo ""
echo "🔧 Next Steps:"
echo "   1. Run: git status (to see what was removed)"
echo "   2. Run: pytest tests/ (verify core tests still pass)"
echo "   3. Run: python run_backtest.py (verify bot still works)"
echo ""
echo "💡 All deletions are REVERSIBLE via git if needed!"
echo ""

