"""Broker limits provider for LIVE mode.

Placeholder for future broker API integration.
Currently raises NotImplementedError to prevent accidental LIVE usage.
"""

from datetime import datetime

from .provider import LimitsProvider, TradingSession, LimitsProviderError


class BrokerLimitsProvider(LimitsProvider):
    """Broker limits provider for LIVE mode.
    
    Placeholder implementation that will integrate with broker APIs
    to retrieve real-time limits from funded account providers.
    
    This is a stub - broker integration is not yet implemented.
    """
    
    def __init__(self, broker_name: str, account_id: str):
        """Initialize broker limits provider.
        
        Args:
            broker_name: Broker name (e.g., "topstep", "apex")
            account_id: Account identifier
        """
        self.broker_name = broker_name
        self.account_id = account_id
    
    def get_daily_loss_limit(self, timestamp: datetime) -> float:
        """Get daily loss limit from broker API.
        
        Args:
            timestamp: Current timestamp
            
        Returns:
            Daily loss limit from broker
            
        Raises:
            LimitsProviderError: If broker API call fails
            NotImplementedError: Until broker integration is complete
        """
        raise NotImplementedError(
            f"Broker limits provider not yet implemented for {self.broker_name}. "
            "Use DeterministicLimitsProvider for LIVE_DRY testing."
        )
    
    def get_trading_session(self, timestamp: datetime) -> TradingSession:
        """Get trading session from broker API.
        
        Args:
            timestamp: Current timestamp
            
        Returns:
            TradingSession from broker
            
        Raises:
            LimitsProviderError: If broker API call fails
            NotImplementedError: Until broker integration is complete
        """
        raise NotImplementedError(
            f"Broker limits provider not yet implemented for {self.broker_name}. "
            "Use DeterministicLimitsProvider for LIVE_DRY testing."
        )

