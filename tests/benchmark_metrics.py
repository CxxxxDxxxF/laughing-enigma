"""Benchmark for metrics computation optimization."""
import time
import random
import numpy as np
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.metrics import Metrics
from src.engines.simple import RawReturns

def generate_returns(n=1000):
    """Generate random returns list."""
    return [random.uniform(-0.01, 0.01) for _ in range(n)]

def benchmark_metrics():
    """Benchmark Metrics.compute."""
    returns_list = generate_returns(10000)
    # Create RawReturns object
    raw_returns = RawReturns(
        dates=["2024-01-01"] * len(returns_list), # Dummy dates
        returns=returns_list,
        initial_capital=10000.0,
        final_value=11000.0
    )
    
    # Run once to warm up (compile regex/load libs)
    Metrics.compute("warmup", raw_returns)
    
    start_time = time.time()
    for _ in range(100):
        Metrics.compute("bench", raw_returns)
    end_time = time.time()
    
    duration = end_time - start_time
    print(f"Metrics.compute 100 times (10k returns): {duration:.4f}s")
    
if __name__ == "__main__":
    benchmark_metrics()
