"""Structured JSON Logger Configuration.

This module provides a configured logger that outputs standard logs to stderr
and structured JSON logs to a rolling file handler.
"""
import logging
import logging.handlers
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

# Ensure logs directory exists
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "app.json"

class JSONFormatter(logging.Formatter):
    """Format logs as JSON."""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format the log record as a valid JSON string."""
        log_entry = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "line": record.lineno
        }
        
        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
            
        # Merge extra fields if passed (e.g. logger.info("msg", extra={"context": bla}))
        if hasattr(record, "metadata"):
             log_entry["metadata"] = record.metadata
             
        return json.dumps(log_entry)

def setup_logger(name: str = "app", level: int = logging.INFO) -> logging.Logger:
    """Setup and return a configured logger.
    
    Args:
        name: Name of the logger
        level: Logging level
        
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Avoid duplicate handlers
    if logger.handlers:
        return logger
        
    # 1. Console Handler (Pretty/Standard)
    # console_handler = logging.StreamHandler(sys.stderr)
    # console_formatter = logging.Formatter(
    #     '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    # )
    # console_handler.setFormatter(console_formatter)
    # logger.addHandler(console_handler)
    
    # 2. JSON File Handler (Rotating)
    file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=10*1024*1024, backupCount=5 # 10MB
    )
    json_formatter = JSONFormatter()
    file_handler.setFormatter(json_formatter)
    logger.addHandler(file_handler)
    
    # Also log to stdout for Docker/Supervisor aggregation capability, but keep it readable?
    # Actually, let's keep console simpler.
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
    logger.addHandler(console_handler)
    
    return logger

# Global logger instance (can be imported directly)
logger = setup_logger()
