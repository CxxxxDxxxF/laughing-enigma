# ID Determinism Audit (Step 6.1)

## Summary

Found UUID usage in engine internals that needs to be made deterministic for LIVE mode.

## Findings

### UUID Usage Locations

#### 1. `src/execution/paper_engine.py`
- **Line 83**: `session_id = str(uuid.uuid4())` - Session ID generation
- **Line 194**: `order_id = str(uuid.uuid4())` - Order ID for HOLD signals
- **Line 211**: `order_id = str(uuid.uuid4())` - Order ID for instrument mismatch
- **Line 228**: `order_id = str(uuid.uuid4())` - Order ID for instrument not allowed
- **Line 244**: `order_id = str(uuid.uuid4())` - Order ID for accepted orders (main path)
- **Line 339**: `fill_id = str(uuid.uuid4())` - Fill ID generation

#### 2. `src/execution/fill.py`
- **Line 50**: `filled_at = datetime.now()` - Fallback timestamp (already handled by clock)

#### 3. `src/execution/position.py`
- **Line 42**: `updated_at = datetime.now()` - Fallback timestamp (already handled by clock)

#### 4. `src/execution/order.py`
- **Line 81**: `created_at = datetime.now()` - Fallback timestamp (already handled by clock)

## Solution: ID Provider Abstraction

Created `src/execution/id_provider.py` with:

- **IDProvider** abstract base class
- **SimulationIDProvider** - uses UUIDs (SIMULATION mode)
- **DeterministicIDProvider** - generates deterministic IDs (LIVE/LIVE_DRY mode)

### ID Generation Strategy

For deterministic IDs:
- **order_id**: `{cycle_id}_order_{signal_id or index}`
- **fill_id**: `{order_id}_fill_{fill_index}`
- **session_id**: `{cycle_id}_session`

### Integration Required

1. **Modify PaperExecutionEngine.__init__** to accept `id_provider: Optional[IDProvider]`
2. **Replace all `str(uuid.uuid4())` calls** with:
   - `self.id_provider.generate_order_id(signal_id=signal.strategy_id, index=i)`
   - `self.id_provider.generate_fill_id(order_id=order.id, fill_index=0)`
   - `self.id_provider.generate_session_id(cycle_id=cycle_id)`
3. **Update runner.py** to inject DeterministicIDProvider in LIVE/LIVE_DRY mode:
   ```python
   if _is_live_mode(execution_mode):
       base_engine.id_provider = DeterministicIDProvider(prefix=cycle_id)
   ```

### Status

- ✅ ID provider abstraction created
- ⚠️ Not yet integrated into engine (requires engine modifications)
- 📝 Documented for future implementation

## Notes

- Session IDs: Can be deterministic from cycle_id
- Order IDs: Can be deterministic from signal.strategy_id + cycle_id
- Fill IDs: Can be deterministic from order_id + fill_index

This is a quick fix once integrated - the abstraction is ready, just needs wiring.

