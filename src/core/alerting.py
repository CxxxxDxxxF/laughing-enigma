"""Alerting system for critical notifications.

Manages sending alerts to configured channels (e.g. Discord, Console).
"""
import os
import json
import logging
import requests
from typing import Optional, Dict, Any
from enum import Enum
from .logger import setup_logger

# Use our structured logger
logger = setup_logger("alerting")

class AlertLevel(Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

class AlertManager:
    """Manages dispatch of alerts to configured providers."""
    
    def __init__(self):
        """Initialize AlertManager."""
        self.webhook_url = os.getenv("ALERT_WEBHOOK_URL")
        self.enabled = bool(self.webhook_url)
        
    def send(self, 
             title: str, 
             message: str, 
             level: AlertLevel = AlertLevel.INFO,
             metadata: Optional[Dict[str, Any]] = None):
        """Send an alert to all configured channels.
        
        Args:
            title: Short title of the alert
            message: Detailed message body
            level: Severity level
            metadata: Optional dictionary of context
        """
        # Always log to application logs
        log_msg = f"ALERT: [{level.value}] {title} - {message}"
        if level in (AlertLevel.ERROR, AlertLevel.CRITICAL):
            logger.error(log_msg, extra={"metadata": metadata})
        else:
            logger.info(log_msg, extra={"metadata": metadata})
            
        # Dispatch to Webhook if enabled
        if self.enabled:
            self._send_webhook(title, message, level, metadata)
            
    def _send_webhook(self, title: str, message: str, level: AlertLevel, metadata: Optional[Dict[str, Any]]):
        """Send alert to webhook (e.g. Discord/Slack)."""
        try:
            # Simple Discord-compatible format
            color = 3447003 # Blue
            if level == AlertLevel.WARNING: color = 16776960 # Yellow
            if level == AlertLevel.ERROR: color = 15158332 # Red
            elif level == AlertLevel.CRITICAL: color = 10038562 # Dark Red

            payload = {
                "embeds": [{
                    "title": f"[{level.value}] {title}",
                    "description": message,
                    "color": color,
                    "fields": [],
                    "footer": {"text": "Trading System Alert"}
                }]
            }
            
            if metadata:
                for k, v in metadata.items():
                    payload["embeds"][0]["fields"].append({
                        "name": str(k),
                        "value": str(v)[:1024], # Limit length
                        "inline": True
                    })

            response = requests.post(self.webhook_url, json=payload, timeout=5.0)
            response.raise_for_status()
            
        except Exception as e:
            logger.error(f"Failed to send webhook alert: {e}")

# Global instance
alert_manager = AlertManager()
