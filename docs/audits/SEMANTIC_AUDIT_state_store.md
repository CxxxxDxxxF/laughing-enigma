# Semantic Audit: src/lifecycle/state_store.py

## 1) File Purpose

This module provides deterministic filesystem-based storage and retrieval of portfolio states across cycles, storing states in JSON format at `artifacts/portfolio/{portfolio_id}/states/{state_id}.json`.

## 2) Data Model

### 2.1 `PortfolioStateStoreError` [L18-L20]
- **Type**: Exception class
- **Purpose**: Error raised when portfolio state store operations fail
- **Methods**: None (inherits from Exception)

### 2.2 `PortfolioStateStore` [L23-L67]
- **Type**: Abstract base class (ABC)
- **Purpose**: Abstract interface for portfolio state storage

#### Method: `load_latest_state()` [L26-L36]
- **Inputs**: 
  - `portfolio_id: str` - Portfolio identifier
- **Outputs**: 
  - `Optional[CurrentPortfolioState]` - Latest state, or None if no state exists
- **Side effects**: None (abstract method)
- **Failure modes**: None (abstract method, raises NotImplementedError if called)
- **Determinism guarantees**: N/A (abstract)

#### Method: `save_state()` [L38-L55]
- **Inputs**: 
  - `portfolio_id: str` - Portfolio identifier
  - `state: CurrentPortfolioState` - Portfolio state to save
  - `state_id: Optional[str] = None` - Optional state identifier (auto-generated if not provided)
- **Outputs**: 
  - `str` - State identifier (provided or auto-generated)
- **Side effects**: None (abstract method)
- **Failure modes**: None (abstract method, raises NotImplementedError if called)
- **Determinism guarantees**: N/A (abstract)

#### Method: `list_states()` [L57-L67]
- **Inputs**: 
  - `portfolio_id: str` - Portfolio identifier
- **Outputs**: 
  - `List[str]` - List of state IDs, sorted by timestamp (most recent first)
- **Side effects**: None (abstract method)
- **Failure modes**: None (abstract method, raises NotImplementedError if called)
- **Determinism guarantees**: N/A (abstract)

### 2.3 `LocalPortfolioStateStore` [L70-L259]
- **Type**: Concrete class (implements PortfolioStateStore)
- **Purpose**: Local filesystem-based portfolio state store implementation

#### Method: `__init__()` [L80-L86]
- **Inputs**: 
  - `artifact_store: ArtifactStore` - ArtifactStore instance
- **Outputs**: None (constructor)
- **Side effects**: 
  - Stores `artifact_store` as instance attribute `self.artifact_store`
- **Failure modes**: None (no validation, no exceptions)
- **Determinism guarantees**: Yes (same inputs → same state)

#### Method: `_get_state_path()` [L88-L98]
- **Inputs**: 
  - `portfolio_id: str` - Portfolio identifier
  - `state_id: str` - State identifier
- **Outputs**: 
  - `str` - Path relative to artifact store base: `"portfolio/{portfolio_id}/states/{state_id}.json"`
- **Side effects**: None (pure function)
- **Failure modes**: None (no validation, string formatting only)
- **Determinism guarantees**: Yes (same inputs → same path string)

#### Method: `load_latest_state()` [L100-L122]
- **Inputs**: 
  - `portfolio_id: str` - Portfolio identifier
- **Outputs**: 
  - `Optional[CurrentPortfolioState]` - Latest state, or None if no states exist
- **Side effects**: 
  - Reads filesystem (calls `list_states()` [L113], then `_load_state()` [L119])
  - Reads JSON file from disk [L150]
- **Failure modes**: 
  - `PortfolioStateStoreError` if `list_states()` raises exception [L121-L122]
  - `PortfolioStateStoreError` if `_load_state()` raises exception (wrapped in try-except [L121-L122])
- **Determinism guarantees**: Yes (given same filesystem state → same result, but depends on `list_states()` determinism)

#### Method: `_load_state()` [L124-L170]
- **Inputs**: 
  - `portfolio_id: str` - Portfolio identifier
  - `state_id: str` - State identifier
- **Outputs**: 
  - `CurrentPortfolioState` - Deserialized state object
- **Side effects**: 
  - Reads filesystem: checks if file exists [L147], reads file bytes [L150], decodes UTF-8 [L150]
  - Imports `DrawdownTracker` if needed [L155]
  - Constructs `CurrentPortfolioState` object [L161-L167]
- **Failure modes**: 
  - `PortfolioStateStoreError` if file does not exist [L147-L148]
  - `PortfolioStateStoreError` if JSON parsing fails (wrapped in try-except [L169-L170])
  - `PortfolioStateStoreError` if datetime parsing fails (wrapped in try-except [L169-L170])
  - `PortfolioStateStoreError` if `DrawdownTracker.from_dict()` fails (wrapped in try-except [L169-L170])
  - Exception if `artifact_store.base_path` is not accessible (not explicitly caught, would bubble up)
- **Determinism guarantees**: Yes (same file contents → same deserialized object, assuming DrawdownTracker.from_dict() is deterministic)

**Deserialization details [L150-L167]**:
- Reads JSON from file [L150]
- Extracts `drawdown_tracker` if present [L154-L156], calls `DrawdownTracker.from_dict()` (UNKNOWN: depends on drawdown.py implementation)
- Extracts `positions_by_instrument` if present [L159] (preserved as dict, no deserialization)
- Constructs `CurrentPortfolioState` with:
  - `strategy_allocations` from JSON [L162]
  - `total_capital` from JSON [L163]
  - `timestamp` from ISO format string [L164]
  - `drawdown_tracker` (may be None) [L165]
  - `positions_by_instrument` (may be None) [L166]

#### Method: `save_state()` [L172-L221]
- **Inputs**: 
  - `portfolio_id: str` - Portfolio identifier
  - `state: CurrentPortfolioState` - Portfolio state to save
  - `state_id: Optional[str] = None` - Optional state identifier
- **Outputs**: 
  - `str` - State identifier (provided or auto-generated)
- **Side effects**: 
  - **State ID generation [L192-L193]**: If `state_id` is None, generates ID as `f"state_{state.timestamp.strftime('%Y%m%d_%H%M%S')}"` (non-deterministic if called at different times with same state)
  - **Serialization [L195-L204]**: 
    - If `state.to_dict()` exists, calls it [L196-L197] (UNKNOWN: depends on CurrentPortfolioState.to_dict() implementation)
    - Otherwise, manually constructs dict [L199-L203] (does NOT include drawdown_tracker or positions_by_instrument)
  - **File write [L204-L216]**: 
    - Converts state dict to JSON with indent=2 [L204]
    - Encodes to UTF-8 bytes [L204]
    - Gets base path from artifact_store.base_path [L208-L212] (falls back to `./artifacts` if base_path not present [L211-L212])
    - Creates parent directories [L215]
    - Writes bytes to file [L216] (overwrites if exists)
- **Failure modes**: 
  - `PortfolioStateStoreError` if any exception occurs during save (wrapped in try-except [L220-L221])
  - Directory creation may fail (OSError, wrapped in exception handler)
  - File write may fail (OSError, wrapped in exception handler)
  - `state.to_dict()` may raise exception (wrapped in exception handler)
- **Determinism guarantees**: 
  - **Partial**: Same inputs with provided `state_id` → same file path and contents
  - **Non-deterministic**: If `state_id` is None, generated ID depends on `state.timestamp` (deterministic for same timestamp, but ID format may collide if two states have same timestamp down to the second)

**Serialization behavior**:
- If `state.to_dict()` exists [L196-L197]: Uses it (UNKNOWN: CurrentPortfolioState.to_dict() includes drawdown_tracker and positions_by_instrument if not None - see planner.py:70-81)
- If `state.to_dict()` does not exist [L199-L203]: Manual dict construction (MISSING: does NOT serialize drawdown_tracker or positions_by_instrument, only strategy_allocations, total_capital, timestamp)

**Overwrite behavior [L216]**: 
- Uses `write_bytes()` which overwrites existing file if `state_id` matches existing file

#### Method: `list_states()` [L223-L259]
- **Inputs**: 
  - `portfolio_id: str` - Portfolio identifier
- **Outputs**: 
  - `List[str]` - List of state IDs (filenames without .json extension), sorted by filename descending (most recent first)
- **Side effects**: 
  - Reads filesystem: accesses `artifact_store.base_path` [L233] (may raise AttributeError if base_path not present, not caught)
  - Lists directory contents [L234-L240]
  - Filters JSON files [L240]
  - Extracts state IDs (filenames) [L243]
- **Failure modes**: 
  - `PortfolioStateStoreError` if any exception occurs (wrapped in try-except [L258-L259])
  - AttributeError if `artifact_store.base_path` does not exist (not explicitly caught, would be wrapped by exception handler)
  - OSError if directory access fails (wrapped in exception handler)
- **Determinism guarantees**: Yes (same filesystem state → same list, but sorting is by filename string comparison, not by actual timestamp)

**Filtering logic [L245-L256]**:
- **Primary [L247-L252]**: Filters to only state IDs ending with `'_after'`, sorts by filename descending
- **Fallback [L254-L256]**: If no `'_after'` states exist, returns all state IDs sorted by filename descending
- **Sorting**: Uses string sort (`reverse=True`), assumes filename format allows chronological ordering (e.g., timestamp-based or lexicographic)

**Assumption**: Filenames sort chronologically when sorted lexicographically in reverse (e.g., `state_20240101_120000_after` > `state_20240101_110000_after`)

## 3) Persistence Contract

### 3.1 Exact On-Disk Paths

**Path template**: `{base_path}/portfolio/{portfolio_id}/states/{state_id}.json`

- **base_path**: 
  - From `artifact_store.base_path` if attribute exists [L140, L208]
  - Fallback to `Path("./artifacts")` if attribute does not exist [L143, L212]
  - UNKNOWN: Whether other ArtifactStore implementations have base_path attribute

- **portfolio_id**: Provided as parameter (string, no validation)

- **states subdirectory**: Hardcoded as `"states"` [L98, L234]

- **state_id**: 
  - Provided by caller, or
  - Auto-generated as `f"state_{state.timestamp.strftime('%Y%m%d_%H%M%S')}"` [L193]
  - Format: `state_YYYYMMDD_HHMMSS` (e.g., `state_20240101_120000`)
  - Extension: Always `.json` [L98, L216]

**Example paths**:
- `artifacts/portfolio/demo_portfolio/states/state_20240101_120000.json`
- `artifacts/portfolio/demo_portfolio/states/cycle_20240101_120000_before.json` (if state_id provided with `_before` suffix)
- `artifacts/portfolio/demo_portfolio/states/cycle_20240101_120000_after.json` (if state_id provided with `_after` suffix)

### 3.2 Naming Rules

**State ID constraints**:
- No explicit validation of `state_id` format
- Must be filesystem-safe (no path separators, etc.)
- File extension `.json` is appended automatically [L98]
- State IDs are used as filenames directly (after appending `.json`)

**Auto-generation rules [L192-L193]**:
- Triggered when `state_id` parameter is None
- Format: `state_{YYYYMMDD_HHMMSS}` where timestamp comes from `state.timestamp`
- Collision risk: Two states with same timestamp (down to second) will generate same ID and overwrite

**Special naming conventions** (assumed by `list_states()`):
- States ending with `'_after'` are considered "completed" states [L247]
- States ending with `'_before'` are considered "snapshot" states (filtered out by `list_states()`)
- Sorting assumes lexicographic ordering reflects chronological ordering

### 3.3 ID Generation vs Provided

**Provided IDs**: 
- Used directly if `state_id` parameter is not None [L192]
- No validation, no sanitization
- Used as-is for filename (with `.json` extension)

**Auto-generated IDs**:
- Generated only when `state_id` is None [L192-L193]
- Format: `state_{state.timestamp.strftime('%Y%m%d_%H%M%S')}`
- Generated from `state.timestamp` (datetime object)
- Deterministic: Same timestamp → same ID
- Non-deterministic across calls: Different calls with same state object still use state.timestamp (deterministic if timestamp unchanged)

### 3.4 Overwrite vs Append Behavior

**Overwrite behavior [L216]**:
- Uses `Path.write_bytes()` which overwrites existing file if path exists
- No versioning, no append mode
- No check for existing file before write
- Silent overwrite: No warning if file already exists

**Implications**:
- Same `state_id` → file is overwritten
- Auto-generated IDs with same timestamp → potential overwrite (collision)
- No atomic write (no temp file + rename pattern)
- Partial write on failure: File may be left in corrupted state if exception occurs mid-write

## 4) State Integrity

### 4.1 Invariants Enforced

**Invariant 1: File Existence Check Before Load [L147-L148]**
- **Statement**: `_load_state()` checks file exists before attempting read
- **Enforcement**: Explicit `if not full_path.exists()` check [L147]
- **Violation handling**: Raises `PortfolioStateStoreError` with message

**Invariant 2: Directory Creation Before Write [L215]**
- **Statement**: Parent directories are created before file write
- **Enforcement**: `full_path.parent.mkdir(parents=True, exist_ok=True)` [L215]
- **Violation handling**: Exception caught and wrapped in PortfolioStateStoreError [L220-L221]

**Invariant 3: JSON Encoding Consistency [L204]**
- **Statement**: All state files use UTF-8 encoding with indent=2
- **Enforcement**: `json.dumps(..., indent=2).encode('utf-8')` [L204]
- **Violation handling**: JSON encoding errors would be caught by exception handler

**Invariant 4: Latest State is Most Recent '_after' State [L245-L252]**
- **Statement**: `load_latest_state()` returns only states ending with `'_after'` (if any exist)
- **Enforcement**: Filtering logic in `list_states()` [L247]
- **Violation handling**: Falls back to all states if no `'_after'` states exist [L254-L256]

### 4.2 Invariants Assumed (Not Enforced)

**Assumed Invariant 1: State ID Uniqueness**
- **Statement**: Each state_id should be unique within a portfolio
- **Enforcement**: None (no check before write, overwrites silently)
- **What breaks if violated**: States overwrite each other, history lost

**Assumed Invariant 2: Portfolio ID Validity**
- **Statement**: `portfolio_id` is a valid filesystem path component
- **Enforcement**: None (no validation, no sanitization)
- **What breaks if violated**: Invalid paths, filesystem errors, security issues

**Assumed Invariant 3: State ID Filesystem Safety**
- **Statement**: `state_id` is filesystem-safe (no path separators, special chars)
- **Enforcement**: None (no sanitization)
- **What breaks if violated**: Invalid paths, filesystem errors, security issues

**Assumed Invariant 4: Timestamp Monotonicity**
- **Statement**: States have monotonically increasing timestamps
- **Enforcement**: None (no validation)
- **What breaks if violated**: `list_states()` sorting may not reflect chronological order if filenames don't sort chronologically

**Assumed Invariant 5: CurrentPortfolioState.to_dict() Completeness**
- **Statement**: If `state.to_dict()` exists, it serializes all required fields (including drawdown_tracker and positions_by_instrument)
- **Enforcement**: None (relies on CurrentPortfolioState implementation)
- **What breaks if violated**: If `to_dict()` is missing fields, they won't be persisted; if fallback manual dict is used [L199-L203], drawdown_tracker and positions_by_instrument are lost

**Assumed Invariant 6: DrawdownTracker Serialization Roundtrip**
- **Statement**: `DrawdownTracker.to_dict()` and `DrawdownTracker.from_dict()` are inverse operations
- **Enforcement**: None (depends on drawdown.py implementation)
- **What breaks if violated**: Tracker state lost or corrupted on save/load

**Assumed Invariant 7: Positions Dict Structure**
- **Statement**: `positions_by_instrument` is a dict of dicts (Position.to_dict() results) that can be serialized/deserialized as-is
- **Enforcement**: None (no validation, no conversion)
- **What breaks if violated**: If Position objects need special handling, they won't be reconstructed correctly (only dict preserved)

**Assumed Invariant 8: ArtifactStore.base_path Existence**
- **Statement**: `artifact_store` has `base_path` attribute (or fallback to `./artifacts` is acceptable)
- **Enforcement**: Partial (checks with `hasattr()` [L140, L208], falls back [L143, L212])
- **What breaks if violated**: If base_path doesn't exist and fallback is wrong directory, states saved/loaded from wrong location

**Assumed Invariant 9: Filename Lexicographic Order = Chronological Order**
- **Statement**: Sorting state IDs by filename (reverse=True) produces chronological order (most recent first)
- **Enforcement**: None (assumes naming convention)
- **What breaks if violated**: `list_states()` returns states in wrong order, `load_latest_state()` returns wrong state

**Assumed Invariant 10: JSON File Format Validity**
- **Statement**: All `.json` files in states directory are valid state files
- **Enforcement**: None (no schema validation)
- **What breaks if violated**: Corrupted or malformed files cause deserialization failures

## 5) Replayability

### 5.1 Full Replay Analysis

**Given**: A directory of state files at `{base_path}/portfolio/{portfolio_id}/states/*.json`

**Replay capability**: **PARTIAL** - States can be loaded, but full replay requires additional information.

### 5.2 What Can Be Replayed

**State reconstruction [L124-L170]**:
- ✅ `strategy_allocations` (dict) - fully reconstructible
- ✅ `total_capital` (float) - fully reconstructible  
- ✅ `timestamp` (datetime) - fully reconstructible from ISO format
- ✅ `drawdown_tracker` (DrawdownTracker) - reconstructible if `DrawdownTracker.from_dict()` works correctly (UNKNOWN: depends on drawdown.py)
- ✅ `positions_by_instrument` (dict) - reconstructible as dict, but Position objects not reconstructed (only dict preserved)

### 5.3 Missing Information for Full Replay

**Missing 1: Position Object Reconstruction**
- **Issue**: `positions_by_instrument` is stored as dict of dicts [L159, L166], not as Position objects
- **Impact**: Positions can be read as dicts but not used as Position instances without manual reconstruction
- **Location**: [L159, L166] - no `Position.from_dict()` call

**Missing 2: State ID to Cycle Mapping**
- **Issue**: No explicit mapping from state_id to cycle_id
- **Impact**: Cannot determine which cycle a state belongs to without parsing state_id naming convention
- **Location**: States are stored by state_id, no cycle_id metadata in file

**Missing 3: State Relationship (Before/After)**
- **Issue**: `_before` and `_after` states are linked by naming convention only (both have cycle_id prefix)
- **Impact**: Cannot programmatically determine which `_before` corresponds to which `_after` without parsing filenames
- **Location**: [L245-L256] - filtering logic assumes naming convention but doesn't preserve relationships

**Missing 4: Cycle Context**
- **Issue**: States don't contain references to evaluation_id, allocation_id, rebalance_plan_id, execution_id
- **Impact**: Cannot replay full cycle context (which evaluation/allocation/plan/execution produced this state)
- **Location**: CurrentPortfolioState doesn't include cycle artifacts (by design, but limits replayability)

**Missing 5: Survivability Control Events**
- **Issue**: Control events that modified allocations/positions are not stored in state
- **Impact**: Cannot replay exact modifications (e.g., position size caps applied)
- **Location**: States store final values, not modification history

**Missing 6: Rules Violations History**
- **Issue**: Rules violations from validation are not stored in state
- **Impact**: Cannot replay which rules were violated during state transitions
- **Location**: States don't include violation history

### 5.4 Deterministic Replay Conditions

**For deterministic replay, need**:
1. ✅ Same state files (JSON content)
2. ✅ Same `DrawdownTracker.from_dict()` implementation (UNKNOWN: depends on drawdown.py)
3. ⚠️ Position reconstruction logic (if Position objects needed, must manually call `Position.from_dict()` on each dict in `positions_by_instrument`)
4. ❌ Cycle artifact IDs (evaluation_id, allocation_id, etc.) - not stored
5. ❌ Cycle configuration - not stored
6. ❌ Execution results - not stored

**Conclusion**: State files allow **state reconstruction** but not **full cycle replay** without additional artifacts (cycle results, execution results, etc.).

## 6) Unknowns

### UNKNOWN: Line 155 - `DrawdownTracker.from_dict()` implementation
- **Symbol**: `DrawdownTracker.from_dict()`
- **What must be inspected**: `src/rules/drawdown.py` - `DrawdownTracker.from_dict()` method
- **Reason**: Cannot determine exact deserialization logic, what fields are required/optional, failure modes, determinism

### UNKNOWN: Line 156 - `DrawdownTracker.from_dict()` return value structure
- **Symbol**: `DrawdownTracker` object structure
- **What must be inspected**: `src/rules/drawdown.py` - `DrawdownTracker` class definition
- **Reason**: Cannot determine what fields/methods DrawdownTracker has, what invariants it maintains

### UNKNOWN: Line 196 - `CurrentPortfolioState.to_dict()` implementation
- **Symbol**: `state.to_dict()`
- **What must be inspected**: `src/rebalance/planner.py` - `CurrentPortfolioState.to_dict()` method (lines 70-81)
- **Reason**: Cannot determine exact serialization logic, what fields are included, format of nested objects

### UNKNOWN: Line 140, 208 - `ArtifactStore.base_path` attribute contract
- **Symbol**: `artifact_store.base_path`
- **What must be inspected**: `src/core/artifacts.py` - `ArtifactStore` and `LocalArtifactStore` classes
- **Reason**: Cannot determine if all ArtifactStore implementations have base_path attribute, or if fallback behavior is correct

### UNKNOWN: Line 159, 166 - `positions_by_instrument` dict structure
- **Symbol**: `positions_by_instrument` dict values
- **What must be inspected**: `src/execution/position.py` - `Position.to_dict()` method to understand dict structure
- **Reason**: Cannot determine exact dict structure, required fields, whether Position.from_dict() can reconstruct from it

### UNKNOWN: Line 233 - `artifact_store.base_path` type and guarantees
- **Symbol**: `artifact_store.base_path`
- **What must be inspected**: `src/core/artifacts.py` - `LocalArtifactStore.base_path` attribute type (Path vs str)
- **Reason**: Line 233 uses it directly as Path, but `hasattr()` check suggests it may not exist - need to verify type and existence guarantees

### UNKNOWN: Line 240 - Filesystem glob behavior with special characters
- **Symbol**: `states_dir.glob("*.json")`
- **What must be inspected**: Python pathlib.Path.glob() documentation and filesystem behavior
- **Reason**: Cannot determine behavior with filenames containing special characters, unicode, or if glob pattern matches correctly in all cases

### UNKNOWN: Line 247 - Filename sorting with mixed naming conventions
- **Symbol**: `sid.endswith('_after')` and `sort(reverse=True)`
- **What must be inspected**: Actual state file naming patterns in use
- **Reason**: Cannot determine if all state files follow expected naming pattern, whether sorting produces correct chronological order in all cases

