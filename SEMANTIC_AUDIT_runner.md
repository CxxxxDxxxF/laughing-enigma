# Semantic Audit: src/lifecycle/runner.py

## 1) File Purpose

This file orchestrates the complete portfolio lifecycle cycle: evaluation → allocation → rebalance planning → rebalance execution. It is pure orchestration with no business logic, only wiring existing components together. The file ensures determinism: same configs + same data → same cycle result, with no background state or mutable globals.

## 2) Execution Entrypoints

### 2.1 CLI Entrypoint: `main()` (lines 1195-1327)

**Call chain:**
1. `main()` (line 1195)
   - Parses CLI arguments (--config, --artifacts-dir)
   - Calls `PortfolioCycleConfig.from_json_file()` (line 1257)
   - Creates `LocalArtifactStore` (line 1260)
   - Creates `SimpleResearchEngine` (line 1263)
   - Creates execution engine factory (lambda function, lines 1273-1277)
   - Creates `LocalPortfolioStateStore` (line 1280)
   - Calls `run_portfolio_cycle()` (lines 1283-1289)
   - Calls `persist_cycle_result()` (line 1292)
   - Prints summary and exits

### 2.2 Programmatic Entrypoint: `run_portfolio_cycle()` (lines 308-1168)

**Direct callable function** - main orchestration function for running a portfolio cycle.

**Call chain (when called programmatically):**
- External code → `run_portfolio_cycle()` → various sub-modules (evaluation, allocation, rebalance, execution)

### 2.3 Helper Entrypoint: `persist_cycle_result()` (lines 1171-1192)

**Direct callable function** - persists a CycleResult to artifact store.

**Call chain:**
- `persist_cycle_result(result, artifact_store)`
  - Calls `result.to_dict()` (line 1188)
  - Calls `artifact_store.store()` (line 1189)

### 2.4 Config Factory Entrypoints

- `PortfolioCycleConfig.from_dict()` (lines 95-185) - Creates config from dictionary
- `PortfolioCycleConfig.from_json_file()` (lines 187-209) - Creates config from JSON file
- `PortfolioCycleConfig.to_dict()` (lines 211-248) - Serializes config to dictionary

## 3) Data Model Map

### 3.1 `CycleError` (lines 56-58)
- **Type**: Exception class
- **Purpose**: Error raised when portfolio cycle execution fails
- **Fields**: None (inherits from Exception)
- **Set by**: Raised at lines 183, 185, 205, 207, 209, 1168, 1192
- **Read by**: Exception handlers in `main()` (lines 1318, 1321)
- **Persisted**: No
- **None allowed**: N/A

### 3.2 `PortfolioCycleConfig` (lines 61-248)
- **Type**: dataclass
- **Purpose**: Configuration for a complete portfolio cycle

**Fields:**

- `portfolio_id: str` (line 82)
  - **Set by**: `from_dict()` (line 169), `from_json_file()` → `from_dict()`
  - **Read by**: `run_portfolio_cycle()` (lines 375, 383, 392, 454, 478, 492, 500, 502, 527, 528, 548, 561, 564, 568, 571-576, 642, 650, 658, 660, 688, 691, 695, 703, 714, 719, 765, 779, 795, 806, 812, 824, 928, 933, 934, 1004, 1013, 1042, 1064, 1119, 1147, 1151, 1161, 1163)
  - **Persisted**: Yes, via `to_dict()` (line 231)
  - **None allowed**: No (required field)

- `evaluation_config: BatchEvaluationConfig` (line 83)
  - **Set by**: `from_dict()` (line 114), `from_json_file()` → `from_dict()`
  - **Read by**: `run_portfolio_cycle()` (line 497), `to_dict()` (line 214), `main()` (line 1267)
  - **Persisted**: Yes, via `to_dict()` (line 214)
  - **None allowed**: No (required field)

- `allocation_config: AllocationConfig` (line 84)
  - **Set by**: `from_dict()` (lines 117-126), `from_json_file()` → `from_dict()`
  - **Read by**: `run_portfolio_cycle()` (lines 474, 508, 519, 537, 639, 681, 684, 1046, 1089, 1129, 1130, 1131, 1132), `to_dict()` (lines 215-223)
  - **Persisted**: Yes, via `to_dict()` (lines 215-223)
  - **None allowed**: No (required field)

- `rebalance_config: RebalanceConfig` (line 85)
  - **Set by**: `from_dict()` (lines 128-134), `from_json_file()` → `from_dict()`
  - **Read by**: `run_portfolio_cycle()` (line 612), `to_dict()` (lines 225-230)
  - **Persisted**: Yes, via `to_dict()` (lines 225-230)
  - **None allowed**: No (required field)

- `execution_config: Dict[str, Any]` (line 86)
  - **Set by**: `from_dict()` (line 173), `from_json_file()` → `from_dict()`
  - **Read by**: `run_portfolio_cycle()` (lines 564, 703, 779, 872, 933), `to_dict()` (line 232)
  - **Persisted**: Yes, via `to_dict()` (line 232)
  - **None allowed**: No (required field, but dict may be empty)

- `cadence_config: Optional[CycleCadenceConfig]` (line 87)
  - **Set by**: `from_dict()` (lines 137-145), `from_json_file()` → `from_dict()` (None if not in data)
  - **Read by**: `run_portfolio_cycle()` (lines 428, 429, 436, 443), `to_dict()` (lines 233-237)
  - **Persisted**: Yes, via `to_dict()` (lines 233-237, None serialized as None)
  - **None allowed**: Yes - None means no cadence check

- `guardrails_config: Optional[GuardrailsConfig]` (line 88)
  - **Set by**: `from_dict()` (lines 148-158), `from_json_file()` → `from_dict()` (None if not in data)
  - **Read by**: `run_portfolio_cycle()` (lines 514, 516, 520, 616, 617, 620, 720, 721, 725), `to_dict()` (lines 238-244)
  - **Persisted**: Yes, via `to_dict()` (lines 238-244, None serialized as None)
  - **None allowed**: Yes - None means no guardrails

- `ruleset_type: Optional[str]` (line 89)
  - **Set by**: `from_dict()` (line 161), `from_json_file()` → `from_dict()` (None if not in data)
  - **Read by**: `run_portfolio_cycle()` (lines 557, 658, 765, 928), `to_dict()` (line 245)
  - **Persisted**: Yes, via `to_dict()` (line 245)
  - **None allowed**: Yes - None means no ruleset validation

- `ruleset_config: Optional[Dict[str, Any]]` (line 90)
  - **Set by**: `from_dict()` (line 162), `from_json_file()` → `from_dict()` (None if not in data)
  - **Read by**: `run_portfolio_cycle()` (lines 561, 660, 765, 768, 931), `to_dict()` (line 246)
  - **Persisted**: Yes, via `to_dict()` (line 246)
  - **None allowed**: Yes - None means no ruleset config (required if ruleset_type is set)

- `cycle_id: Optional[str]` (line 91)
  - **Set by**: `from_dict()` (line 178), `from_json_file()` → `from_dict()`, `run_portfolio_cycle()` parameter (line 314)
  - **Read by**: `run_portfolio_cycle()` (line 363), `to_dict()` (line 247)
  - **Persisted**: Yes, via `to_dict()` (line 247)
  - **None allowed**: Yes - auto-generated if not provided (line 363)

- `validation_hold_quantity: bool` (line 92)
  - **Set by**: `from_dict()` (line 165, default False), `from_json_file()` → `from_dict()`
  - **Read by**: `run_portfolio_cycle()` (lines 317, 482, 487, 492, 495, 507, 514, 551, 608, 616, 653, 658, 700, 719, 775, 839, 1064, 1126, 1138)
  - **Persisted**: Not in `to_dict()` (missing from serialization)
  - **None allowed**: No (bool, default False)

- `validation_bootstrap_first_cycle: bool` (line 93)
  - **Set by**: `from_dict()` (line 166, default True), `from_json_file()` → `from_dict()`
  - **Read by**: `run_portfolio_cycle()` (lines 317, 484, 489)
  - **Persisted**: Not in `to_dict()` (missing from serialization)
  - **None allowed**: No (bool, default True)

### 3.3 `CycleResult` (lines 251-305)
- **Type**: dataclass
- **Purpose**: Result of a complete portfolio cycle

**Fields:**

- `cycle_id: str` (line 270)
  - **Set by**: `run_portfolio_cycle()` (lines 362-363, 399, 451, 525, 627, 668, 731, 1033, 1148)
  - **Read by**: `to_dict()` (line 290), `persist_cycle_result()` (line 1189)
  - **Persisted**: Yes, via `to_dict()` (line 290)
  - **None allowed**: No (required field)

- `cycle_timestamp: datetime` (line 271)
  - **Set by**: `run_portfolio_cycle()` (line 365, used in all CycleResult constructions)
  - **Read by**: `to_dict()` (line 291)
  - **Persisted**: Yes, via `to_dict()` (line 291, ISO format)
  - **None allowed**: No (required field)

- `portfolio_id: str` (line 272)
  - **Set by**: `run_portfolio_cycle()` (from `config.portfolio_id`, lines 402, 454, 528, 629, 671, 734, 1036, 1151)
  - **Read by**: `to_dict()` (line 292)
  - **Persisted**: Yes, via `to_dict()` (line 292)
  - **None allowed**: No (required field)

- `evaluation_id: Optional[str]` (line 273)
  - **Set by**: `run_portfolio_cycle()` (line 494 if skipped, line 502 if executed, lines 403, 456, 529, 630, 672, 735, 1037, 1152)
  - **Read by**: `to_dict()` (line 293), `main()` (line 1299)
  - **Persisted**: Yes, via `to_dict()` (line 293)
  - **None allowed**: Yes - None if evaluation skipped (hold-quantity mode or cadence skip)

- `allocation_id: Optional[str]` (line 274)
  - **Set by**: `run_portfolio_cycle()` (line 506 if skipped, lines 524, 553, 603 if executed, lines 404, 457, 530, 631, 673, 736, 1038, 1153)
  - **Read by**: `to_dict()` (line 294), `main()` (line 1301)
  - **Persisted**: Yes, via `to_dict()` (line 294)
  - **None allowed**: Yes - None if allocation skipped (hold-quantity mode) or halted before persistence

- `rebalance_plan_id: Optional[str]` (line 275)
  - **Set by**: `run_portfolio_cycle()` (line 607 if skipped, lines 625, 655 if executed, lines 405, 458, 532, 632, 674, 737, 1039, 1154)
  - **Read by**: `to_dict()` (line 295), `main()` (line 1303)
  - **Persisted**: Yes, via `to_dict()` (line 295)
  - **None allowed**: Yes - None if rebalance planning skipped (hold-quantity mode) or halted before persistence

- `rebalance_execution_id: Optional[str]` (line 276)
  - **Set by**: `run_portfolio_cycle()` (line 698 if skipped, lines 730, 761 if executed, lines 406, 459, 533, 633, 675, 738, 1040, 1155)
  - **Read by**: `to_dict()` (line 296), `main()` (line 1305)
  - **Persisted**: Yes, via `to_dict()` (line 296)
  - **None allowed**: Yes - None if execution skipped (hold-quantity mode) or halted before persistence

- `state_before_id: Optional[str]` (line 277)
  - **Set by**: `run_portfolio_cycle()` (lines 383, 479 if state_store provided, lines 407, 460, 534, 634, 676, 739, 1041, 1156)
  - **Read by**: `to_dict()` (line 297), `main()` (line 1307)
  - **Persisted**: Yes, via `to_dict()` (line 297)
  - **None allowed**: Yes - None if no previous state or no state_store provided

- `state_after_id: Optional[str]` (line 278)
  - **Set by**: `run_portfolio_cycle()` (line 1119 if state_store provided and cycle completed, lines 408, 461, 535, 635, 677, 740, 1042, 1157)
  - **Read by**: `to_dict()` (line 298), `main()` (line 1309)
  - **Persisted**: Yes, via `to_dict()` (line 298)
  - **None allowed**: Yes - None if cycle skipped/halted or no state_store provided

- `summary: Dict[str, Any]` (line 279)
  - **Set by**: `run_portfolio_cycle()` (lines 409, 462, 535-542, 636-643, 678-686, 741-750, 1043-1051, 1126-1145)
  - **Read by**: `to_dict()` (line 299), `main()` (lines 1312-1314)
  - **Persisted**: Yes, via `to_dict()` (line 299)
  - **None allowed**: No (required field, but dict may be empty)

- `status: str` (line 280)
  - **Set by**: `run_portfolio_cycle()` (always set in CycleResult constructions: "halted" lines 410, 462, 543, 645, 687, 751, 1053, or "skipped" line 462, or "completed" line 1159)
  - **Read by**: `to_dict()` (line 300), `main()` (lines 1297, 1311)
  - **Persisted**: Yes, via `to_dict()` (line 300)
  - **None allowed**: No (required field, values: "completed", "skipped", "halted")

- `skip_reason: Optional[str]` (line 281)
  - **Set by**: `run_portfolio_cycle()` (lines 411, 463, 544, 646, 688, 752, 1054, 1160)
  - **Read by**: `to_dict()` (line 301), `main()` (line 1298)
  - **Persisted**: Yes, via `to_dict()` (line 301)
  - **None allowed**: Yes - None if cycle completed successfully

- `rules_violations: List[Dict[str, Any]]` (line 282, default None)
  - **Set by**: `run_portfolio_cycle()` (lines 412-420, 464, 545, 647, 689, 753, 1055, 1161, initialized line 368)
  - **Read by**: `to_dict()` (line 302)
  - **Persisted**: Yes, via `to_dict()` (line 302, empty list if None)
  - **None allowed**: Yes - converted to empty list in `to_dict()` (line 302)

- `ruleset_type: Optional[str]` (line 283)
  - **Set by**: `run_portfolio_cycle()` (from `config.ruleset_type`, lines 421, 465, 547, 649, 691, 755, 1057, 1162)
  - **Read by**: `to_dict()` (line 303)
  - **Persisted**: Yes, via `to_dict()` (line 303)
  - **None allowed**: Yes - None if no ruleset configured

- `ruleset_config: Optional[Dict[str, Any]]` (line 284)
  - **Set by**: `run_portfolio_cycle()` (from `config.ruleset_config`, lines 422, 466, 548, 650, 692, 756, 1058, 1163)
  - **Read by**: `to_dict()` (line 304)
  - **Persisted**: Yes, via `to_dict()` (line 304)
  - **None allowed**: Yes - None if no ruleset configured

- `survivability_control_events: List[Dict[str, Any]]` (line 285, default None)
  - **Set by**: `run_portfolio_cycle()` (lines 556, 600, 845, 981-984, 1164)
  - **Read by**: `to_dict()` (not included in serialization - missing from `to_dict()`)
  - **Persisted**: No (missing from `to_dict()` method, lines 287-305)
  - **None allowed**: Yes - None if no control events occurred

### 3.4 Type Aliases and Enums (imported)

- `RulesViolation` (imported line 53) - from `..rules`
  - **Fields**: code, message, severity, metadata
  - **Set by**: Ruleset validation methods (lines 663, 838, 1028)
  - **Read by**: Converted to dict via `to_dict()` (lines 689, 1055, 1161)

- `RulesViolationSeverity` (imported line 53) - Enum from `..rules`
  - **Values**: WARN, HALT
  - **Read by**: Filtering for halt violations (lines 666, 1031)

- `CurrentPortfolioState` (imported line 40) - from `..rebalance.planner`
  - **Fields**: strategy_allocations, total_capital, timestamp, drawdown_tracker, positions_by_instrument
  - **Set by**: `state_store.load_latest_state()` (line 375), constructed (lines 385-391, 472-477, 1087-1093, 1111-1117)
  - **Read by**: Used throughout `run_portfolio_cycle()` for planning and state management

- `AllocationResult` (imported line 34) - from `..allocation.allocator`
  - **Fields**: allocation_id, allocation_timestamp, config, total_capital, allocated_capital, unallocated_capital, allocations, metrics
  - **Set by**: `allocate_capital()` (line 508)
  - **Read by**: Used for rebalance planning (line 610), state creation (lines 1067-1070)

- `RebalancePlan` (imported line 39) - from `..rebalance.planner`
  - **Fields**: plan_id, plan_timestamp, trade_intents, metrics
  - **Set by**: `plan_rebalance()` (line 609)
  - **Read by**: Used for execution (line 712), validation (line 662), metrics extraction (lines 619, 643, 685, 749, 1050, 1135)

- `RebalanceExecutionResult` (imported line 45) - from `..rebalance.executor`
  - **Fields**: execution_id, execution_timestamp, plan_id, intent_results, execution_summary, mapping
  - **Set by**: `execute_rebalance_plan()` (line 712)
  - **Read by**: Used for guardrails (lines 723-725), validation (lines 829-837), summary construction (lines 748, 1051, 1136)

- `StrategyEvaluation` (imported line 29) - from `..evaluation.batch`
  - **Fields**: evaluation_id, evaluation_timestamp, ranked_results, results, summary
  - **Set by**: `run_batch_evaluation()` (line 496)
  - **Read by**: Used for allocation (line 509), summary construction (lines 536, 637, 679, 742, 1044, 1128)

## 4) Cycle Timeline (the core)

### Step-by-step ordered timeline of `run_portfolio_cycle()` (lines 308-1168)

#### Phase 0: Initialization (lines 362-369)
- **Function**: `run_portfolio_cycle()` initialization
- **Inputs consumed**: `cycle_id` parameter, `config.cycle_id`
- **Outputs produced**: `cycle_id` (str, auto-generated if None), `cycle_timestamp` (datetime.now()), initialized `rules_violations` list, `state_before_id`, `state_after_id` set to None
- **Side effects**: None
- **Failure modes**: None (deterministic)
- **Deterministic**: Partially - `datetime.now()` is non-deterministic (timestamp generation)

#### Phase 0.1: State Loading (lines 372-394)
- **Function**: `state_store.load_latest_state()` (if state_store provided)
- **Inputs consumed**: `config.portfolio_id`
- **Outputs produced**: `current_state` (CurrentPortfolioState or None)
- **Side effects**: None (read-only)
- **Failure modes**: Exception if state_store raises error
- **Deterministic**: Yes (given same portfolio_id and state store contents)

**If current_state exists (lines 382-393):**
- **Function**: `state_store.save_state()` (save state_before snapshot)
- **Inputs consumed**: `config.portfolio_id`, `current_state`, `cycle_id`
- **Outputs produced**: `state_before_id` (str)
- **Side effects**: Disk write to `portfolio/{portfolio_id}/states/{cycle_id}_before.json`
- **Failure modes**: Exception if state_store raises error
- **Deterministic**: Yes (same inputs → same path)

#### Phase 0.2: Time Reversal Guard (lines 395-424)
- **Function**: Timestamp comparison check
- **Inputs consumed**: `cycle_timestamp`, `current_state.timestamp` (if exists)
- **Outputs produced**: CycleResult with status="halted" if time reversal detected
- **Side effects**: Returns early (cycle halted)
- **Failure modes**: Early return if `cycle_timestamp < current_state.timestamp`
- **Deterministic**: Yes (comparison is deterministic)

#### Phase 0.3: Cadence Check (lines 426-468)
- **Function**: `check_cadence()` (if cadence_config provided)
- **Inputs consumed**: `config.cadence_config`, `current_state.timestamp` (if exists), `cycle_timestamp`
- **Outputs produced**: `should_run` (bool), `skip_reason` (str or None)
- **Side effects**: None (read-only check)
- **Failure modes**: Early return with status="skipped" if cadence check fails
- **Deterministic**: Yes (same timestamps → same result)

**If cadence check fails (lines 449-468):**
- **Function**: Early return
- **Outputs produced**: CycleResult with status="skipped"
- **Side effects**: Returns early (cycle skipped)
- **Failure modes**: None (normal path)

#### Phase 0.4: Initialize Empty State (lines 470-479)
- **Function**: State initialization if no previous state
- **Inputs consumed**: `config.allocation_config.total_capital`, `cycle_timestamp`
- **Outputs produced**: `current_state` (CurrentPortfolioState with empty allocations)
- **Side effects**: If state_store provided, saves initial state (line 479)
- **Failure modes**: Exception if state_store.save_state() fails
- **Deterministic**: Yes

#### Phase 0.5: Hold-Quantity Mode Decision (lines 481-490)
- **Function**: Mode decision logic
- **Inputs consumed**: `config.validation_hold_quantity`, `config.validation_bootstrap_first_cycle`, `current_state.strategy_allocations`
- **Outputs produced**: `should_use_hold_quantity_mode` (bool), `is_first_cycle` (bool), `use_normal_cycle` (bool)
- **Side effects**: Print statements (debug output, lines 487-490)
- **Failure modes**: None
- **Deterministic**: Yes

#### Phase 1: Batch Evaluation (lines 492-502)
- **Function**: `run_batch_evaluation()` (if `use_normal_cycle`)
- **Inputs consumed**: `config.evaluation_config`, `research_engine`, `artifact_store`, `execution_engine_factory`
- **Outputs produced**: `evaluation` (StrategyEvaluation), `evaluation_id` (str)
- **Side effects**: 
  - Disk writes via `run_batch_evaluation()`:
    - `runs/{batch_id}/batch_summary.json`
    - `runs/{batch_id}/results_index.json`
    - Individual evaluation artifacts
- **Failure modes**: Exception if `run_batch_evaluation()` fails
- **Deterministic**: UNKNOWN: Depends on `run_batch_evaluation()` implementation

**If hold-quantity mode (lines 493-494):**
- Evaluation skipped, `evaluation` and `evaluation_id` remain None

#### Phase 2: Capital Allocation (lines 504-603)
- **Function**: `allocate_capital()` (if `use_normal_cycle`)
- **Inputs consumed**: `evaluation`, `config.allocation_config`
- **Outputs produced**: `allocation_result` (AllocationResult), `allocation_id` (str)
- **Side effects**: None (computation only)
- **Failure modes**: Exception if `allocate_capital()` fails
- **Deterministic**: UNKNOWN: Depends on `allocate_capital()` implementation

**Allocation Guardrails Check (lines 513-549)**
- **Function**: `check_allocation_guardrails()` (if guardrails_config and use_normal_cycle)
- **Inputs consumed**: `config.guardrails_config`, `allocation_result.allocations`, `allocation_result.total_capital`
- **Outputs produced**: `passes` (bool), `violation` (str or None)
- **Side effects**: None (read-only check)
- **Failure modes**: Early return with status="halted" if guardrails fail
- **Deterministic**: Yes (same inputs → same result)

**If guardrails fail (lines 521-549):**
- **Function**: `persist_allocation()` then early return
- **Side effects**: Disk write to `runs/{allocation_id}/allocation.json`
- **Outputs produced**: CycleResult with status="halted"

**Allocation Persistence (lines 551-553)**
- **Function**: `persist_allocation()` (if use_normal_cycle and guardrails passed)
- **Inputs consumed**: `allocation_result`, `artifact_store`
- **Outputs produced**: `allocation_id` (str)
- **Side effects**: Disk write to `runs/{allocation_id}/allocation.json`
- **Failure modes**: Exception if persistence fails
- **Deterministic**: Yes (same inputs → same path)

**Survivability Controls (lines 555-603)**
- **Function**: `apply_survivability_controls()` (if ruleset_type=="topstep" and ruleset_config has max_position_size)
- **Inputs consumed**: `allocation_result`, `config.execution_config.price_by_strategy_or_instrument`, `config.ruleset_config.max_position_size`, instrument (from execution engine factory)
- **Outputs produced**: Modified `allocation_result`, `survivability_control_events` (List[Dict])
- **Side effects**: 
  - Creates temporary execution engine (line 572) to extract instrument
  - Modifies `allocation_result` in-place (clamps allocations)
  - Repersists allocation (line 603)
- **Failure modes**: Exception if control application fails
- **Deterministic**: UNKNOWN: Depends on `apply_survivability_controls()` implementation

#### Phase 3: Rebalance Planning (lines 605-655)
- **Function**: `plan_rebalance()` (if `use_normal_cycle`)
- **Inputs consumed**: `allocation_result`, `current_state`, `config.rebalance_config`
- **Outputs produced**: `rebalance_plan` (RebalancePlan), `rebalance_plan_id` (str)
- **Side effects**: None (computation only)
- **Failure modes**: Exception if `plan_rebalance()` fails
- **Deterministic**: UNKNOWN: Depends on `plan_rebalance()` implementation

**Rebalance Guardrails Check (lines 615-651)**
- **Function**: `check_rebalance_guardrails()` (if guardrails_config)
- **Inputs consumed**: `config.guardrails_config`, `rebalance_plan.metrics.total_turnover`, `current_state.total_capital`
- **Outputs produced**: `passes` (bool), `violation` (str or None)
- **Side effects**: None (read-only check)
- **Failure modes**: Early return with status="halted" if guardrails fail
- **Deterministic**: Yes (same inputs → same result)

**If guardrails fail (lines 622-651):**
- **Function**: `persist_rebalance_plan()` then early return
- **Side effects**: Disk write to `runs/{rebalance_plan_id}/rebalance_plan.json`
- **Outputs produced**: CycleResult with status="halted"

**Rebalance Plan Persistence (lines 653-655)**
- **Function**: `persist_rebalance_plan()` (if use_normal_cycle and guardrails passed)
- **Inputs consumed**: `rebalance_plan`, `artifact_store`
- **Outputs produced**: `rebalance_plan_id` (str)
- **Side effects**: Disk write to `runs/{rebalance_plan_id}/rebalance_plan.json`
- **Failure modes**: Exception if persistence fails
- **Deterministic**: Yes (same inputs → same path)

**Ruleset Plan Validation (lines 657-693)**
- **Function**: `ruleset.validate_plan()` (if ruleset_type=="topstep" and use_normal_cycle)
- **Inputs consumed**: `rebalance_plan`, `current_state`, `config.ruleset_config`
- **Outputs produced**: `plan_violations` (List[RulesViolation])
- **Side effects**: Updates `rules_violations` list (line 663)
- **Failure modes**: 
  - Early return with status="halted" if HALT violations found (lines 667-693)
  - Exception if validation fails
- **Deterministic**: UNKNOWN: Depends on `ruleset.validate_plan()` implementation

#### Phase 4: Rebalance Execution (lines 695-761)
- **Function**: `execute_rebalance_plan()` (if `use_normal_cycle`)
- **Inputs consumed**: `rebalance_plan`, `execution_engine` (from factory), `config.execution_config.price_by_strategy_or_instrument`, `mapper` (RebalanceSignalMapper)
- **Outputs produced**: `execution_result` (RebalanceExecutionResult), `rebalance_execution_id` (str)
- **Side effects**: 
  - Creates execution engine via factory (line 701)
  - Executes orders through execution engine (mutates execution engine state)
  - Disk writes via `execute_rebalance_plan()` (fills, orders, positions, etc.)
- **Failure modes**: Exception if `execute_rebalance_plan()` fails
- **Deterministic**: UNKNOWN: Depends on `execute_rebalance_plan()` implementation and execution engine

**Execution Guardrails Check (lines 719-757)**
- **Function**: `check_execution_guardrails()` (if guardrails_config and use_normal_cycle)
- **Inputs consumed**: `config.guardrails_config`, `execution_result.execution_summary` (successful_intents, failed_intents, total_intents)
- **Outputs produced**: `passes` (bool), `violation` (str or None)
- **Side effects**: None (read-only check)
- **Failure modes**: Early return with status="halted" if guardrails fail (execution already occurred)
- **Deterministic**: Yes (same inputs → same result)

**If guardrails fail (lines 727-757):**
- **Function**: `persist_rebalance_execution()` then early return
- **Side effects**: Disk write to `runs/{rebalance_execution_id}/rebalance_execution.json`
- **Outputs produced**: CycleResult with status="halted", state_after_id=None (state not updated)

**Execution Persistence (lines 759-761)**
- **Function**: `persist_rebalance_execution()` (if use_normal_cycle and guardrails passed)
- **Inputs consumed**: `execution_result`, `artifact_store`
- **Outputs produced**: `rebalance_execution_id` (str)
- **Side effects**: Disk write to `runs/{rebalance_execution_id}/rebalance_execution.json`
- **Failure modes**: Exception if persistence fails
- **Deterministic**: Yes (same inputs → same path)

#### Phase 4.5: Ruleset Execution Validation (lines 763-1059)
- **Function**: `ruleset.validate_execution()` (if ruleset_type=="topstep")
- **Inputs consumed**: `execution_result` (or dummy in hold-quantity mode), `current_state`, `execution_engine`, `current_prices`, `day_boundary`, `skip_equity_recalculation` (hold-quantity mode only)
- **Outputs produced**: `exec_violations` (List[RulesViolation])

**Normal Mode Path (lines 819-838)**
- **Side effects**: 
  - May update `current_state.drawdown_tracker` in-place (UNKNOWN: depends on ruleset implementation)
  - Constructs `day_boundary` (line 823)
- **Failure modes**: Exception if validation fails
- **Deterministic**: UNKNOWN: Depends on `ruleset.validate_execution()` implementation

**Hold-Quantity Mode Path (lines 839-1028)**
- **Function**: Mark-to-market equity calculation and validation
- **Inputs consumed**: `current_state.positions_by_instrument`, `current_state.total_capital`, `config.execution_config.price_by_strategy_or_instrument`, `cycle_timestamp`
- **Outputs produced**: 
  - `computed_equity` (float)
  - `positions` (Dict[str, Position]) - reconstructed from state
  - `exec_violations` (List[RulesViolation])
- **Side effects**: 
  - Updates `current_state.drawdown_tracker` in-place via `update()` (lines 908-914)
  - Creates dummy execution engine with positions (line 988-990)
  - Creates dummy execution result (lines 995-1002)
  - May clamp positions if max_position_size exceeded (lines 928-984)
  - Updates `survivability_control_events` (lines 981-984)
- **Failure modes**: 
  - AssertionError if positions/prices missing (lines 866-868)
  - Exception if equity calculation fails
- **Deterministic**: Yes (same prices → same equity calculation)

**HALT Violation Check (lines 1030-1059)**
- **Function**: Filter violations by severity
- **Inputs consumed**: `exec_violations`
- **Outputs produced**: CycleResult with status="halted" if HALT violations found
- **Side effects**: Returns early if halted (state not updated)
- **Failure modes**: Early return
- **Deterministic**: Yes

#### Phase 5: State Update (lines 1061-1123)
- **Function**: `state_store.save_state()` (if state_store provided)

**Normal Mode Path (lines 1064-1093)**
- **Inputs consumed**: 
  - `allocation_result.allocations` (for new allocations)
  - `allocation_result.total_capital` (for total_capital)
  - `current_state.drawdown_tracker` (preserved if ruleset was used)
  - `execution_engine.positions` (for positions_by_instrument)
  - `cycle_timestamp`
- **Outputs produced**: `new_state` (CurrentPortfolioState), `state_after_id` (str)
- **Side effects**: 
  - Disk write to `portfolio/{portfolio_id}/states/{cycle_id}_after.json`
  - Extracts positions from execution engine (lines 1080-1084)
- **Failure modes**: Exception if state_store.save_state() fails
- **Deterministic**: Yes (same inputs → same path)

**Hold-Quantity Mode Path (lines 1094-1117)**
- **Inputs consumed**: 
  - `current_state.strategy_allocations` (preserved)
  - `computed_equity` (for total_capital)
  - `current_state.drawdown_tracker` (updated from validation phase)
  - `current_state.positions_by_instrument` (preserved)
  - `cycle_timestamp`
- **Outputs produced**: `new_state` (CurrentPortfolioState), `state_after_id` (str)
- **Side effects**: Disk write to `portfolio/{portfolio_id}/states/{cycle_id}_after.json`
- **Failure modes**: Exception if state_store.save_state() fails, NameError if computed_equity not set (lines 1106-1108)
- **Deterministic**: Yes (same inputs → same path)

#### Phase 6: Summary Construction (lines 1125-1145)
- **Function**: Build cycle summary dict
- **Inputs consumed**: `evaluation.summary`, `allocation_result`, `rebalance_plan.metrics`, `execution_result.execution_summary` (normal mode) or `current_state.positions_by_instrument` (hold-quantity mode)
- **Outputs produced**: `summary` (Dict[str, Any])
- **Side effects**: None (computation only)
- **Failure modes**: None
- **Deterministic**: Yes (same inputs → same summary)

#### Phase 7: Return Result (lines 1147-1165)
- **Function**: Construct and return CycleResult
- **Inputs consumed**: All collected IDs, timestamps, summary, violations, events
- **Outputs produced**: `CycleResult` with status="completed"
- **Side effects**: None
- **Failure modes**: None
- **Deterministic**: Yes (same inputs → same result)

#### Exception Handling (lines 1167-1168)
- **Function**: Catch-all exception handler
- **Side effects**: Wraps exception in CycleError
- **Failure modes**: All exceptions converted to CycleError

## 5) Guardrails and Rules

### 5.1 Time Reversal Guard (lines 395-424)
- **When it runs**: After loading current state, before cadence check
- **Condition**: `cycle_timestamp < current_state.timestamp`
- **Severity**: HALT (hard stop)
- **After HALT**: 
  - Returns CycleResult with status="halted"
  - `state_before_id` is set (state snapshot saved)
  - `state_after_id` is None (state not updated)
  - No artifacts persisted (evaluation, allocation, rebalance, execution all None)
  - Rules violation recorded with code="TIME_REVERSAL"

### 5.2 Cadence Check (lines 426-468)
- **When it runs**: After time reversal check, before evaluation
- **Function**: `check_cadence()` (from `cadence.py`)
- **Condition**: Time since last cycle < minimum required interval
- **Severity**: SKIP (not a violation, but prevents execution)
- **After SKIP**: 
  - Returns CycleResult with status="skipped"
  - `state_before_id` is set (if state existed)
  - `state_after_id` is None
  - No artifacts persisted
  - `skip_reason` contains cadence message

### 5.3 Allocation Guardrails (lines 513-549)
- **When it runs**: After allocation computation, before allocation persistence
- **Function**: `check_allocation_guardrails()` (from `guardrails.py`)
- **Conditions checked**: 
  - `max_single_strategy_allocation_fraction` exceeded
- **Severity**: HALT (hard stop)
- **After HALT**: 
  - `allocation_id` is persisted (partial artifact saved)
  - `evaluation_id` is set (evaluation completed)
  - Returns CycleResult with status="halted"
  - `state_after_id` is None (state not updated)
  - `skip_reason` contains guardrail violation message

### 5.4 Rebalance Guardrails (lines 615-651)
- **When it runs**: After rebalance planning, before plan persistence (if guardrails_config provided)
- **Function**: `check_rebalance_guardrails()` (from `guardrails.py`)
- **Conditions checked**: 
  - `max_turnover_pct_per_cycle` exceeded (turnover > max_turnover_pct_per_cycle * total_capital)
- **Severity**: HALT (hard stop)
- **After HALT**: 
  - `rebalance_plan_id` is persisted (partial artifact saved)
  - `allocation_id` is set
  - `evaluation_id` is set
  - Returns CycleResult with status="halted"
  - `state_after_id` is None (state not updated)
  - `skip_reason` contains guardrail violation message

### 5.5 Execution Guardrails (lines 719-757)
- **When it runs**: After execution completion, before execution persistence (if guardrails_config and use_normal_cycle)
- **Function**: `check_execution_guardrails()` (from `guardrails.py`)
- **Conditions checked**: 
  - `max_failed_intents` exceeded
  - `min_execution_success_rate` not met
- **Severity**: HALT (hard stop)
- **After HALT**: 
  - **Note**: Execution already occurred (side effects happened)
  - `rebalance_execution_id` is persisted (partial artifact saved)
  - All previous artifacts are set (evaluation, allocation, plan)
  - Returns CycleResult with status="halted"
  - `state_after_id` is None (state not updated despite execution)
  - `skip_reason` contains guardrail violation message

### 5.6 Ruleset Plan Validation (lines 657-693)
- **When it runs**: After rebalance planning and plan persistence, before execution (if ruleset_type=="topstep" and use_normal_cycle)
- **Function**: `ruleset.validate_plan()` (from ruleset implementation)
- **Conditions checked**: UNKNOWN - depends on ruleset implementation (e.g., TopstepRuleset)
- **Severity**: WARN or HALT (per RulesViolation.severity)
- **After WARN**: Violations added to `rules_violations` list, cycle continues
- **After HALT**: 
  - `rebalance_plan_id` is persisted (already persisted before validation)
  - All previous artifacts are set
  - Returns CycleResult with status="halted"
  - `state_after_id` is None
  - `skip_reason` contains first HALT violation message
  - `rules_violations` contains all violations (converted to dicts)

### 5.7 Ruleset Execution Validation (lines 763-1059)
- **When it runs**: After execution completion and execution persistence (if ruleset_type=="topstep")
- **Function**: `ruleset.validate_execution()` (from ruleset implementation)
- **Conditions checked**: UNKNOWN - depends on ruleset implementation
- **Severity**: WARN or HALT (per RulesViolation.severity)
- **After WARN**: Violations added to `rules_violations` list, cycle continues
- **After HALT**: 
  - **Note**: Execution already occurred (side effects happened)
  - `rebalance_execution_id` is persisted (already persisted before validation)
  - All previous artifacts are set
  - Returns CycleResult with status="halted"
  - `state_after_id` is None (state not updated despite execution)
  - `skip_reason` contains first HALT violation message
  - `rules_violations` contains all violations (converted to dicts)

**Normal Mode (lines 819-838)**
- Uses actual `execution_result` and `execution_engine`
- May update `current_state.drawdown_tracker` in-place (UNKNOWN: depends on ruleset)

**Hold-Quantity Mode (lines 839-1028)**
- Computes mark-to-market equity from `current_state.positions_by_instrument` and current prices
- Updates `current_state.drawdown_tracker` with computed equity (lines 908-914)
- Creates dummy execution result for validation
- Uses `skip_equity_recalculation=True` parameter if supported (line 1016)

## 6) Persistence and Artifacts

### 6.1 State Before Snapshot
- **Triggered at**: Lines 382-393 (if current_state exists)
- **Path formation**: `portfolio/{portfolio_id}/states/{cycle_id}_before.json`
- **Naming scheme**: `{cycle_id}_before` (line 392)
- **Data written**: 
  - `strategy_allocations` (dict)
  - `total_capital` (float)
  - `timestamp` (ISO string, preserved from current_state)
  - `drawdown_tracker` (if exists, serialized)
  - `positions_by_instrument` (if exists, dict of Position dicts)
- **Data not written**: N/A (full state snapshot)
- **Nondeterminism sources**: `cycle_id` contains timestamp (line 363) if auto-generated

### 6.2 Initial State Snapshot
- **Triggered at**: Line 479 (if no previous state and state_store provided)
- **Path formation**: `portfolio/{portfolio_id}/states/{state_id}.json` (state_id auto-generated by state_store)
- **Naming scheme**: Auto-generated by `state_store.save_state()` (UNKNOWN: depends on implementation, likely timestamp-based)
- **Data written**: 
  - `strategy_allocations` (empty dict)
  - `total_capital` (from config.allocation_config.total_capital)
  - `timestamp` (cycle_timestamp)
  - `drawdown_tracker` (None)
  - `positions_by_instrument` (None)
- **Data not written**: N/A (initial state)
- **Nondeterminism sources**: Auto-generated state_id (timestamp-based, UNKNOWN exact format)

### 6.3 Evaluation Artifacts
- **Triggered at**: Line 496 (`run_batch_evaluation()`)
- **Path formation**: UNKNOWN - managed by `run_batch_evaluation()` and artifact_store
- **Naming scheme**: `batch_{timestamp}` or provided batch_id
- **Data written**: UNKNOWN - depends on `run_batch_evaluation()` implementation (likely batch_summary.json, results_index.json, individual evaluation results)
- **Data not written**: N/A (managed by evaluation module)
- **Nondeterminism sources**: Timestamp in batch_id if auto-generated (UNKNOWN exact location)

### 6.4 Allocation Artifact
- **Triggered at**: Lines 524, 553, 603 (`persist_allocation()`)
- **Path formation**: `runs/{allocation_id}/allocation.json` (UNKNOWN - managed by `persist_allocation()`)
- **Naming scheme**: `alloc_{timestamp}` or provided allocation_id
- **Data written**: UNKNOWN - depends on `persist_allocation()` implementation (likely AllocationResult serialized)
- **Data not written**: N/A (managed by allocation module)
- **Nondeterminism sources**: Timestamp in allocation_id if auto-generated (UNKNOWN exact location)

### 6.5 Rebalance Plan Artifact
- **Triggered at**: Lines 625, 655 (`persist_rebalance_plan()`)
- **Path formation**: `runs/{rebalance_plan_id}/rebalance_plan.json` (UNKNOWN - managed by `persist_rebalance_plan()`)
- **Naming scheme**: UNKNOWN - depends on `persist_rebalance_plan()` implementation
- **Data written**: UNKNOWN - depends on `persist_rebalance_plan()` implementation (likely RebalancePlan serialized)
- **Data not written**: N/A (managed by rebalance planner module)
- **Nondeterminism sources**: UNKNOWN - depends on plan_id generation

### 6.6 Rebalance Execution Artifact
- **Triggered at**: Lines 730, 761 (`persist_rebalance_execution()`)
- **Path formation**: `runs/{rebalance_execution_id}/rebalance_execution.json` (UNKNOWN - managed by `persist_rebalance_execution()`)
- **Naming scheme**: UNKNOWN - depends on `persist_rebalance_execution()` implementation
- **Data written**: UNKNOWN - depends on `persist_rebalance_execution()` implementation (likely RebalanceExecutionResult serialized)
- **Data not written**: N/A (managed by rebalance executor module)
- **Nondeterminism sources**: UNKNOWN - depends on execution_id generation

### 6.7 Execution Engine Artifacts
- **Triggered at**: During `execute_rebalance_plan()` (line 712)
- **Path formation**: UNKNOWN - managed by execution engine
- **Naming scheme**: UNKNOWN - managed by execution engine
- **Data written**: UNKNOWN - execution engine may persist fills, orders, positions, risk_limits, session_metadata
- **Data not written**: N/A (managed by execution engine)
- **Nondeterminism sources**: UNKNOWN - depends on execution engine implementation

### 6.8 State After Snapshot
- **Triggered at**: Line 1119 (if state_store provided and cycle completed)
- **Path formation**: `portfolio/{portfolio_id}/states/{cycle_id}_after.json`
- **Naming scheme**: `{cycle_id}_after` (line 1122)
- **Data written**: 
  - **Normal mode (lines 1087-1093)**: 
    - `strategy_allocations` (from allocation_result)
    - `total_capital` (from allocation_result.total_capital)
    - `timestamp` (cycle_timestamp)
    - `drawdown_tracker` (from current_state, updated by ruleset if applicable)
    - `positions_by_instrument` (from execution_engine.positions, converted to dicts)
  - **Hold-quantity mode (lines 1111-1117)**:
    - `strategy_allocations` (preserved from current_state)
    - `total_capital` (computed_equity)
    - `timestamp` (cycle_timestamp)
    - `drawdown_tracker` (from current_state, updated during validation)
    - `positions_by_instrument` (preserved from current_state)
- **Data not written**: 
  - Survivability control events (not included in state, only in CycleResult)
  - Rules violations (not included in state, only in CycleResult)
- **Nondeterminism sources**: `cycle_id` contains timestamp (line 363) if auto-generated

### 6.9 Cycle Result Artifact
- **Triggered at**: Line 1189 (`persist_cycle_result()`)
- **Path formation**: `runs/{cycle_id}/cycle_result.json` (UNKNOWN - managed by artifact_store.store())
- **Naming scheme**: Uses `result.cycle_id`
- **Data written**: 
  - All CycleResult fields via `to_dict()`:
    - `cycle_id`, `cycle_timestamp`, `portfolio_id`
    - `evaluation_id`, `allocation_id`, `rebalance_plan_id`, `rebalance_execution_id`
    - `state_before_id`, `state_after_id`
    - `summary` (dict)
    - `status`, `skip_reason`
    - `rules_violations` (list of dicts, empty list if None)
    - `ruleset_type`, `ruleset_config`
  - **Missing from serialization**: `survivability_control_events` (not in `to_dict()`, line 287-305)
- **Data not written**: 
  - `survivability_control_events` (field exists but not serialized in `to_dict()`)
- **Nondeterminism sources**: `cycle_id` contains timestamp (line 363) if auto-generated

## 7) Invariants

### Invariant 1: Cycle ID Uniqueness
- **Statement**: Each cycle execution must have a unique `cycle_id`
- **Where enforced**: Line 363 (auto-generation with timestamp), or provided via parameter/config
- **What breaks if violated**: State snapshots with `{cycle_id}_before` and `{cycle_id}_after` could overwrite each other, artifact collisions

### Invariant 2: Timestamp Monotonicity
- **Statement**: `cycle_timestamp` must be >= `current_state.timestamp` (if state exists)
- **Where enforced**: Lines 397-424 (time reversal guard)
- **What breaks if violated**: State history becomes inconsistent, drawdown tracking breaks, validation logic may fail

### Invariant 3: State Before Must Precede State After
- **Statement**: If both `state_before_id` and `state_after_id` are set, `state_before_id` represents state at cycle start, `state_after_id` represents state at cycle end
- **Where enforced**: Lines 382-393 (state_before save), 1119 (state_after save)
- **What breaks if violated**: Cannot reconstruct state transitions, audit trail broken

### Invariant 4: Hold-Quantity Mode Requires Positions
- **Statement**: In hold-quantity mode, `current_state.positions_by_instrument` must exist and be non-empty for mark-to-market validation
- **Where enforced**: Line 866 (assertion)
- **What breaks if violated**: Cannot compute equity, validation fails with AssertionError

### Invariant 5: Execution Config Must Have Prices for Hold-Quantity Mode
- **Statement**: In hold-quantity mode, `config.execution_config.price_by_strategy_or_instrument` must contain price for the instrument
- **Where enforced**: Lines 867-868 (assertions)
- **What breaks if violated**: Cannot compute mark-to-market equity, validation fails with AssertionError

### Invariant 6: Normal Cycle Requires Evaluation
- **Statement**: If `use_normal_cycle` is True, `evaluation` must be set (not None) before allocation
- **Where enforced**: Line 509 (allocation uses evaluation)
- **What breaks if violated**: `allocate_capital()` would fail or receive None, causing exception

### Invariant 7: Normal Cycle Requires Allocation Before Planning
- **Statement**: If `use_normal_cycle` is True, `allocation_result` must be set (not None) before rebalance planning
- **Where enforced**: Line 610 (planning uses allocation_result)
- **What breaks if violated**: `plan_rebalance()` would fail or receive None, causing exception

### Invariant 8: Normal Cycle Requires Plan Before Execution
- **Statement**: If `use_normal_cycle` is True, `rebalance_plan` must be set (not None) before execution
- **Where enforced**: Line 712 (execution uses rebalance_plan)
- **What breaks if violated**: `execute_rebalance_plan()` would fail or receive None, causing exception

### Invariant 9: Halted Cycles Do Not Update State
- **Statement**: If cycle status is "halted", `state_after_id` must be None
- **Where enforced**: All early return paths with status="halted" (lines 408, 461, 535, 635, 677, 740, 1042)
- **What breaks if violated**: State would be updated despite violation, breaking audit trail and consistency

### Invariant 10: Ruleset Type Requires Config
- **Statement**: If `config.ruleset_type` is set (not None), `config.ruleset_config` should be set (not None) for ruleset initialization
- **Where enforced**: Lines 658, 765 (ruleset_type checks assume ruleset_config exists if ruleset_type is set)
- **What breaks if violated**: Ruleset initialization would fail if ruleset_config is None but ruleset_type is set

### Invariant 11: Survivability Control Events Must Be Lists
- **Statement**: `survivability_control_events` must be a List[Dict[str, Any]] when set, not None
- **Where enforced**: Lines 556, 845 (initialization as empty list), 1164 (assignment)
- **What breaks if violated**: `to_dict()` would fail or serialize None incorrectly (though field is missing from to_dict anyway)

### Invariant 12: Computed Equity Must Be Set in Hold-Quantity Mode
- **Statement**: In hold-quantity mode with ruleset validation, `computed_equity` must be set before state persistence
- **Where enforced**: Lines 902 (assignment), 1105-1108 (NameError handling, fallback to current_state.total_capital)
- **What breaks if violated**: State persistence would use wrong total_capital value, equity tracking breaks

### Invariant 13: Drawdown Tracker Update Single Point
- **Statement**: In hold-quantity mode, drawdown tracker is updated exactly once (during validation phase, lines 908-914), and `validate_execution()` is called with `skip_equity_recalculation=True` to prevent double-update
- **Where enforced**: Lines 908-914 (single update point), 1016 (skip_equity_recalculation parameter)
- **What breaks if violated**: Tracker would be updated multiple times, equity double-counted, validation inconsistent

### Invariant 14: Execution Engine Factory Creates Isolated Sessions
- **Statement**: `execution_engine_factory()` must create a new, isolated execution engine instance each time it's called
- **Where enforced**: Not enforced in this file (contract with caller)
- **What breaks if violated**: State leaks between evaluations/executions, determinism breaks, results become contaminated

### Invariant 15: Artifact Store Path Determinism
- **Statement**: Artifact store must generate deterministic paths for same (run_id, artifact_name) pairs
- **Where enforced**: Not enforced in this file (contract with ArtifactStore implementation)
- **What breaks if violated**: Artifacts cannot be reliably retrieved, reproducibility breaks

## 8) Unknowns

### UNKNOWN: Line 496 - `run_batch_evaluation()` implementation
- **Symbol**: `run_batch_evaluation()`
- **What must be inspected**: `src/evaluation/batch.py` - `run_batch_evaluation()` function
- **Reason**: Cannot determine exact artifacts written, path formation, determinism guarantees, failure modes

### UNKNOWN: Line 508 - `allocate_capital()` implementation
- **Symbol**: `allocate_capital()`
- **What must be inspected**: `src/allocation/allocator.py` - `allocate_capital()` function
- **Reason**: Cannot determine determinism guarantees, exact computation logic, failure modes

### UNKNOWN: Line 523 - `persist_allocation()` path formation
- **Symbol**: `persist_allocation()`
- **What must be inspected**: `src/allocation/allocator.py` - `persist_allocation()` function
- **Reason**: Cannot determine exact path format, naming scheme, data structure written

### UNKNOWN: Line 552 - `persist_allocation()` (second call)
- **Symbol**: `persist_allocation()`
- **What must be inspected**: Same as above
- **Reason**: Same as above

### UNKNOWN: Line 592 - `apply_survivability_controls()` implementation
- **Symbol**: `apply_survivability_controls()`
- **What must be inspected**: `src/control/survivability_controller.py` - `apply_survivability_controls()` function
- **Reason**: Cannot determine exact allocation modification logic, determinism, failure modes

### UNKNOWN: Line 603 - `persist_allocation()` (third call, after controls)
- **Symbol**: `persist_allocation()`
- **What must be inspected**: Same as line 523
- **Reason**: Same as above

### UNKNOWN: Line 609 - `plan_rebalance()` implementation
- **Symbol**: `plan_rebalance()`
- **What must be inspected**: `src/rebalance/planner.py` - `plan_rebalance()` function
- **Reason**: Cannot determine determinism guarantees, exact planning logic, failure modes

### UNKNOWN: Line 624 - `persist_rebalance_plan()` path formation
- **Symbol**: `persist_rebalance_plan()`
- **What must be inspected**: `src/rebalance/planner.py` - `persist_rebalance_plan()` function
- **Reason**: Cannot determine exact path format, naming scheme, data structure written

### UNKNOWN: Line 654 - `persist_rebalance_plan()` (second call)
- **Symbol**: `persist_rebalance_plan()`
- **What must be inspected**: Same as above
- **Reason**: Same as above

### UNKNOWN: Line 660 - `TopstepRuleset.validate_plan()` implementation
- **Symbol**: `ruleset.validate_plan()`
- **What must be inspected**: `src/rules/topstep.py` - `TopstepRuleset.validate_plan()` method
- **Reason**: Cannot determine exact validation rules, conditions checked, side effects on state

### UNKNOWN: Line 701 - `execution_engine_factory()` implementation
- **Symbol**: `execution_engine_factory()`
- **What must be inspected**: Caller-provided factory function
- **Reason**: Cannot determine exact execution engine creation, isolation guarantees, instrument extraction logic

### UNKNOWN: Line 712 - `execute_rebalance_plan()` implementation
- **Symbol**: `execute_rebalance_plan()`
- **What must be inspected**: `src/rebalance/executor.py` - `execute_rebalance_plan()` function
- **Reason**: Cannot determine exact execution logic, side effects on execution engine, determinism, failure modes

### UNKNOWN: Line 729 - `persist_rebalance_execution()` path formation
- **Symbol**: `persist_rebalance_execution()`
- **What must be inspected**: `src/rebalance/executor.py` - `persist_rebalance_execution()` function
- **Reason**: Cannot determine exact path format, naming scheme, data structure written

### UNKNOWN: Line 760 - `persist_rebalance_execution()` (second call)
- **Symbol**: `persist_rebalance_execution()`
- **What must be inspected**: Same as above
- **Reason**: Same as above

### UNKNOWN: Line 768 - `TopstepRuleset()` constructor
- **Symbol**: `TopstepRuleset(ruleset_config)`
- **What must be inspected**: `src/rules/topstep.py` - `TopstepRuleset.__init__()` method
- **Reason**: Cannot determine exact config parsing, validation, initialization logic

### UNKNOWN: Line 829 - `TopstepRuleset.validate_execution()` implementation (normal mode)
- **Symbol**: `ruleset.validate_execution()`
- **What must be inspected**: `src/rules/topstep.py` - `TopstepRuleset.validate_execution()` method
- **Reason**: Cannot determine exact validation rules, side effects on current_state.drawdown_tracker, determinism

### UNKNOWN: Line 889 - `calculate_portfolio_equity()` implementation
- **Symbol**: `calculate_portfolio_equity()`
- **What must be inspected**: `src/rules/drawdown.py` - `calculate_portfolio_equity()` function
- **Reason**: Cannot determine exact equity calculation formula, determinism

### UNKNOWN: Line 908 - `DrawdownTracker.update()` implementation
- **Symbol**: `current_state.drawdown_tracker.update()`
- **What must be inspected**: `src/rules/drawdown.py` - `DrawdownTracker.update()` method
- **Reason**: Cannot determine exact tracker update logic, side effects, state mutations

### UNKNOWN: Line 1013 - `TopstepRuleset.validate_execution()` implementation (hold-quantity mode)
- **Symbol**: `ruleset.validate_execution()` with `skip_equity_recalculation=True`
- **What must be inspected**: `src/rules/topstep.py` - `TopstepRuleset.validate_execution()` method, specifically `skip_equity_recalculation` parameter handling
- **Reason**: Cannot determine if parameter is honored, what validation still occurs, side effects prevented

### UNKNOWN: Line 1080 - `execution_engine.positions` structure
- **Symbol**: `execution_engine.positions`
- **What must be inspected**: `src/execution/paper_engine.py` - `PaperExecutionEngine.positions` attribute
- **Reason**: Cannot determine exact structure, type, serialization format

### UNKNOWN: Line 1119 - `state_store.save_state()` path formation for state_after
- **Symbol**: `state_store.save_state()`
- **What must be inspected**: `src/lifecycle/state_store.py` - `LocalPortfolioStateStore.save_state()` method
- **Reason**: Cannot determine exact path format when state_id is provided (cycle_id_after), vs auto-generation logic

### UNKNOWN: Line 1189 - `artifact_store.store()` path formation for cycle_result
- **Symbol**: `artifact_store.store()`
- **What must be inspected**: `src/core/artifacts.py` - `LocalArtifactStore.store()` method
- **Reason**: Cannot determine exact path format (likely `runs/{cycle_id}/cycle_result.json` but need to verify)

