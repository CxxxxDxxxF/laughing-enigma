#!/usr/bin/env python3
"""
SUPERVISOR PROCESS
Ensures crypto_surfer.py runs 24/7. Auto-restarts on crash.
"""

import os
import sys
import time
import subprocess
import logging
from pathlib import Path
from datetime import datetime

# Configure Logging
log_dir = Path(__file__).parent.parent / "logs"
log_dir.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] [SUPERVISOR] %(message)s',
    handlers=[
        logging.FileHandler(log_dir / "supervisor.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("Supervisor")

SCRIPT_PATH = Path(__file__).parent / "crypto_surfer.py"

def run_process():
    """Run the bot and monitor it."""
    logger.info(f"Starting bot: {SCRIPT_PATH}")
    
    while True:
        try:
            # Start the process
            cmd = [sys.executable, str(SCRIPT_PATH)]
            process = subprocess.Popen(
                cmd,
                stdout=open(log_dir / "crypto_24_7.log", "a"),
                stderr=subprocess.STDOUT
            )
            
            logger.info(f"Bot started with PID {process.pid}")
            
            # Wait for it to finish/crash
            return_code = process.wait()
            
            # Check exit code
            if return_code == 0:
                logger.info("Bot exited gracefully (0). Restarting in 60s...")
            else:
                logger.error(f"Bot crashed with code {return_code}. Restarting in 10s...")
            
            # Backoff before restart
            time.sleep(10 if return_code != 0 else 60)
            
        except KeyboardInterrupt:
            logger.info("Supervisor stopped by user.")
            if 'process' in locals() and process.poll() is None:
                process.terminate()
            break
        except Exception as e:
            logger.error(f"Supervisor error: {e}")
            time.sleep(30)

if __name__ == "__main__":
    run_process()
