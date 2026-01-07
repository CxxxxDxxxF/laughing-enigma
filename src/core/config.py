"""Configuration loader for trading system.

Loads environment variables from .env file and provides
typed configuration objects.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Try to load dotenv, but don't fail if not installed
try:
    from dotenv import load_dotenv
    _HAS_DOTENV = True
except ImportError:
    _HAS_DOTENV = False


def load_env(env_path: Optional[Path] = None) -> None:
    """Load environment variables from .env file.
    
    Args:
        env_path: Optional path to .env file. If None, searches
                  project root directory.
    """
    if not _HAS_DOTENV:
        return
    
    if env_path:
        load_dotenv(env_path)
    else:
        # Find project root (where .env should be)
        # Start from this file and go up to find .env
        current = Path(__file__).resolve().parent
        for _ in range(5):  # Max 5 levels up
            env_file = current / ".env"
            if env_file.exists():
                load_dotenv(env_file)
                return
            current = current.parent
        
        # Fallback to default behavior
        load_dotenv()


@dataclass(frozen=True)
class AlpacaConfig:
    """Alpaca API configuration."""
    base_url: str
    api_key: str
    secret_key: str
    
    @classmethod
    def from_env(cls) -> 'AlpacaConfig':
        """Load Alpaca config from environment variables.
        
        Returns:
            AlpacaConfig instance
            
        Raises:
            ValueError: If required environment variables are missing
        """
        load_env()
        
        base_url = os.getenv("ALPACA_BASE_URL", "")
        api_key = os.getenv("ALPACA_API_KEY", "")
        secret_key = os.getenv("ALPACA_SECRET_KEY", "")
        
        missing = []
        if not base_url:
            missing.append("ALPACA_BASE_URL")
        if not api_key:
            missing.append("ALPACA_API_KEY")
        if not secret_key:
            missing.append("ALPACA_SECRET_KEY")
        
        if missing:
            raise ValueError(
                f"Missing required environment variables: {', '.join(missing)}. "
                f"Please ensure your .env file is configured correctly."
            )
        
        return cls(
            base_url=base_url,
            api_key=api_key,
            secret_key=secret_key
        )
    
    @property
    def is_paper(self) -> bool:
        """Check if this is a paper trading configuration."""
        return "paper" in self.base_url.lower()


def get_alpaca_config() -> AlpacaConfig:
    """Get Alpaca configuration from environment.
    
    Convenience function for loading Alpaca config.
    
    Returns:
        AlpacaConfig instance
    """
    return AlpacaConfig.from_env()
