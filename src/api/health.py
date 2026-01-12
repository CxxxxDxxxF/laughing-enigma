"""Health check endpoint for container orchestrators.

Provides a simple HTTP endpoint for Kubernetes/Docker health probes.
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import threading
from datetime import datetime
from typing import Callable, Optional


class HealthCheckHandler(BaseHTTPRequestHandler):
    """Simple HTTP handler for health checks."""
    
    # Class-level health check function
    _health_check: Optional[Callable[[], dict]] = None
    
    def do_GET(self):
        if self.path == "/health" or self.path == "/healthz":
            self._handle_health()
        elif self.path == "/ready" or self.path == "/readyz":
            self._handle_ready()
        else:
            self.send_error(404)
    
    def _handle_health(self):
        """Liveness check - is the process alive?"""
        response = {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat()
        }
        self._send_json(response, 200)
    
    def _handle_ready(self):
        """Readiness check - is the service ready to accept traffic?"""
        if self._health_check:
            try:
                result = self._health_check()
                status_code = 200 if result.get("ready", False) else 503
                self._send_json(result, status_code)
            except Exception as e:
                self._send_json({"ready": False, "error": str(e)}, 503)
        else:
            self._send_json({"ready": True, "timestamp": datetime.utcnow().isoformat()}, 200)
    
    def _send_json(self, data: dict, status_code: int):
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
    
    def log_message(self, format, *args):
        # Suppress default logging
        pass


class HealthCheckServer:
    """Threaded health check server."""
    
    def __init__(self, port: int = 8080, health_check: Optional[Callable[[], dict]] = None):
        self.port = port
        self.server = None
        self.thread = None
        HealthCheckHandler._health_check = health_check
    
    def start(self):
        """Start health check server in background thread."""
        self.server = HTTPServer(("0.0.0.0", self.port), HealthCheckHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self
    
    def stop(self):
        """Stop health check server."""
        if self.server:
            self.server.shutdown()


def create_trading_health_check(runner) -> Callable[[], dict]:
    """Create a health check function for the trading runner.
    
    Args:
        runner: ProductionRunner instance.
        
    Returns:
        Health check function.
    """
    def check():
        return {
            "ready": runner.running,
            "cycles_run": runner.cycles_run,
            "portfolio_id": runner.portfolio_id,
            "mode": runner.execution_mode.value,
            "timestamp": datetime.utcnow().isoformat()
        }
    return check
