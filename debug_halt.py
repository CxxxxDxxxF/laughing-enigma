from src.core.artifacts import LocalArtifactStore
from src.lifecycle.runner import HaltFlagStore
from pathlib import Path
import os

store = LocalArtifactStore(base_path=Path("data/artifacts"))
halt_store = HaltFlagStore(store)
path = halt_store._get_halt_flag_path('test_runner_v1')
print(f"Path: {path}")
print(f"Abs Path: {path.absolute()}")
print(f"Exists: {halt_store.halt_flag_exists('test_runner_v1')}")

if halt_store.halt_flag_exists('test_runner_v1'):
    print("Deleting...")
    halt_store.clear_halt_flag('test_runner_v1')
    print(f"Exists after clear: {halt_store.halt_flag_exists('test_runner_v1')}")
