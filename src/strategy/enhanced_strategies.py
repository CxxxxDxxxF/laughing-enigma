"""Enhanced Dual Momentum Strategy.

Improvements over basic dual momentum:
1. Trend filter: Only buy when price > 200-day SMA
2. Risk-adjusted ranking: Use Sharpe ratio instead of raw returns
3. Volatility scaling: Reduce position size in high volatility
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Optional
from dataclasses import dataclass


@dataclass
class StrategySignal:
    """Output signal from strategy."""
    symbol: str
    action: str  # 'buy', 'sell', 'hold'
    weight: float  # 0.0 to 1.0
    reason: str


class EnhancedDualMomentum:
    """Enhanced Dual Momentum with trend filter and risk adjustment.
    
    Key improvements:
    - 200-day SMA trend filter (only buy in uptrends)
    - Sharpe-based ranking instead of raw returns
    - Volatility-adjusted position sizing
    """
    
    def __init__(
        self,
        lookback_momentum: int = 126,  # 6 months
        lookback_trend: int = 200,  # 200-day SMA
        min_momentum: float = 0.0,  # Minimum momentum to buy
        use_sharpe_ranking: bool = True,
        volatility_target: float = 0.15  # 15% annual vol target
    ):
        self.lookback_momentum = lookback_momentum
        self.lookback_trend = lookback_trend
        self.min_momentum = min_momentum
        self.use_sharpe_ranking = use_sharpe_ranking
        self.volatility_target = volatility_target
    
    def calculate_momentum(self, prices: pd.Series) -> float:
        """Calculate momentum as percentage return."""
        if len(prices) < self.lookback_momentum:
            return 0.0
        
        current = prices.iloc[-1]
        past = prices.iloc[-self.lookback_momentum]
        
        return (current - past) / past
    
    def calculate_sharpe(self, prices: pd.Series, lookback: int = 126) -> float:
        """Calculate rolling Sharpe ratio."""
        if len(prices) < lookback:
            return 0.0
        
        returns = prices.pct_change().dropna().tail(lookback)
        if len(returns) < 20:
            return 0.0
        
        mean_return = returns.mean() * 252  # Annualize
        std_return = returns.std() * np.sqrt(252)
        
        if std_return == 0:
            return 0.0
        
        return mean_return / std_return
    
    def calculate_volatility(self, prices: pd.Series, lookback: int = 21) -> float:
        """Calculate annualized volatility."""
        if len(prices) < lookback:
            return 0.2  # Default 20%
        
        returns = prices.pct_change().dropna().tail(lookback)
        return returns.std() * np.sqrt(252)
    
    def is_uptrend(self, prices: pd.Series) -> bool:
        """Check if price is above 200-day SMA."""
        if len(prices) < self.lookback_trend:
            return False
        
        sma = prices.rolling(self.lookback_trend).mean().iloc[-1]
        current = prices.iloc[-1]
        
        return current > sma
    
    def generate_signals(
        self,
        data: Dict[str, pd.DataFrame],
        current_positions: Optional[Dict[str, float]] = None
    ) -> List[StrategySignal]:
        """Generate trading signals for all symbols.
        
        Args:
            data: Dict mapping symbol -> DataFrame with 'close' column
            current_positions: Dict mapping symbol -> current weight
            
        Returns:
            List of StrategySignal objects
        """
        signals = []
        rankings = []
        
        # Calculate metrics for each symbol
        for symbol, df in data.items():
            if 'close' not in df.columns:
                continue
            
            prices = df['close']
            
            # Check trend filter
            in_uptrend = self.is_uptrend(prices)
            
            # Calculate ranking metric
            if self.use_sharpe_ranking:
                score = self.calculate_sharpe(prices)
            else:
                score = self.calculate_momentum(prices)
            
            # Calculate volatility for position sizing
            volatility = self.calculate_volatility(prices)
            
            rankings.append({
                'symbol': symbol,
                'score': score,
                'in_uptrend': in_uptrend,
                'volatility': volatility,
                'momentum': self.calculate_momentum(prices)
            })
        
        # Sort by score descending
        rankings.sort(key=lambda x: x['score'], reverse=True)
        
        # Generate signals
        total_weight = 0.0
        
        for rank in rankings:
            symbol = rank['symbol']
            
            # Must be in uptrend and have positive momentum
            if rank['in_uptrend'] and rank['momentum'] > self.min_momentum:
                # Volatility-adjusted weight
                raw_weight = 1.0 / len(rankings)
                vol_scalar = min(2.0, max(0.5, self.volatility_target / rank['volatility']))
                weight = raw_weight * vol_scalar
                
                # Cap total at 100%
                if total_weight + weight > 1.0:
                    weight = 1.0 - total_weight
                
                if weight > 0.01:
                    signals.append(StrategySignal(
                        symbol=symbol,
                        action='buy',
                        weight=weight,
                        reason=f"Uptrend + Sharpe={rank['score']:.2f}, Vol={rank['volatility']:.1%}"
                    ))
                    total_weight += weight
            else:
                # Sell or avoid
                reason = []
                if not rank['in_uptrend']:
                    reason.append("below 200-SMA")
                if rank['momentum'] <= self.min_momentum:
                    reason.append(f"low momentum={rank['momentum']:.1%}")
                
                signals.append(StrategySignal(
                    symbol=symbol,
                    action='sell' if current_positions and current_positions.get(symbol, 0) > 0 else 'hold',
                    weight=0.0,
                    reason=", ".join(reason) if reason else "filtered"
                ))
        
        return signals


class RSIMeanReversion:
    """RSI-based mean reversion strategy.
    
    Buy when RSI < oversold threshold
    Sell when RSI > overbought threshold
    """
    
    def __init__(
        self,
        rsi_period: int = 14,
        oversold: float = 30.0,
        overbought: float = 70.0
    ):
        self.rsi_period = rsi_period
        self.oversold = oversold
        self.overbought = overbought
    
    def calculate_rsi(self, prices: pd.Series) -> float:
        """Calculate RSI indicator."""
        if len(prices) < self.rsi_period + 1:
            return 50.0  # Neutral
        
        delta = prices.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)
        
        avg_gain = gain.rolling(self.rsi_period).mean().iloc[-1]
        avg_loss = loss.rolling(self.rsi_period).mean().iloc[-1]
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))
    
    def generate_signals(
        self,
        data: Dict[str, pd.DataFrame],
        current_positions: Optional[Dict[str, float]] = None
    ) -> List[StrategySignal]:
        """Generate mean reversion signals."""
        signals = []
        
        for symbol, df in data.items():
            if 'close' not in df.columns:
                continue
            
            rsi = self.calculate_rsi(df['close'])
            
            if rsi < self.oversold:
                signals.append(StrategySignal(
                    symbol=symbol,
                    action='buy',
                    weight=1.0 / len(data),
                    reason=f"RSI={rsi:.1f} (oversold)"
                ))
            elif rsi > self.overbought:
                signals.append(StrategySignal(
                    symbol=symbol,
                    action='sell',
                    weight=0.0,
                    reason=f"RSI={rsi:.1f} (overbought)"
                ))
            else:
                signals.append(StrategySignal(
                    symbol=symbol,
                    action='hold',
                    weight=current_positions.get(symbol, 0) if current_positions else 0,
                    reason=f"RSI={rsi:.1f} (neutral)"
                ))
        
        return signals


class BollingerBands:
    """Bollinger Bands breakout/mean reversion strategy."""
    
    def __init__(
        self,
        period: int = 20,
        std_dev: float = 2.0,
        mode: str = 'mean_reversion'  # or 'breakout'
    ):
        self.period = period
        self.std_dev = std_dev
        self.mode = mode
    
    def calculate_bands(self, prices: pd.Series) -> tuple:
        """Calculate Bollinger Bands."""
        if len(prices) < self.period:
            return None, None, None
        
        sma = prices.rolling(self.period).mean().iloc[-1]
        std = prices.rolling(self.period).std().iloc[-1]
        
        upper = sma + (std * self.std_dev)
        lower = sma - (std * self.std_dev)
        
        return lower, sma, upper
    
    def generate_signals(
        self,
        data: Dict[str, pd.DataFrame],
        current_positions: Optional[Dict[str, float]] = None
    ) -> List[StrategySignal]:
        """Generate Bollinger Band signals."""
        signals = []
        
        for symbol, df in data.items():
            if 'close' not in df.columns:
                continue
            
            prices = df['close']
            lower, mid, upper = self.calculate_bands(prices)
            
            if lower is None:
                continue
            
            current = prices.iloc[-1]
            
            if self.mode == 'mean_reversion':
                if current <= lower:
                    signals.append(StrategySignal(
                        symbol=symbol,
                        action='buy',
                        weight=1.0 / len(data),
                        reason=f"At lower band (mean reversion)"
                    ))
                elif current >= upper:
                    signals.append(StrategySignal(
                        symbol=symbol,
                        action='sell',
                        weight=0.0,
                        reason=f"At upper band"
                    ))
                else:
                    signals.append(StrategySignal(
                        symbol=symbol,
                        action='hold',
                        weight=current_positions.get(symbol, 0) if current_positions else 0,
                        reason=f"Within bands"
                    ))
            else:  # breakout
                if current > upper:
                    signals.append(StrategySignal(
                        symbol=symbol,
                        action='buy',
                        weight=1.0 / len(data),
                        reason=f"Breakout above upper band"
                    ))
                elif current < lower:
                    signals.append(StrategySignal(
                        symbol=symbol,
                        action='sell',
                        weight=0.0,
                        reason=f"Breakdown below lower band"
                    ))
                else:
                    signals.append(StrategySignal(
                        symbol=symbol,
                        action='hold',
                        weight=current_positions.get(symbol, 0) if current_positions else 0,
                        reason=f"Within bands"
                    ))
        
        return signals


class MovingAverageCrossover:
    """Golden Cross / Death Cross strategy."""
    
    def __init__(
        self,
        fast_period: int = 50,
        slow_period: int = 200
    ):
        self.fast_period = fast_period
        self.slow_period = slow_period
    
    def generate_signals(
        self,
        data: Dict[str, pd.DataFrame],
        current_positions: Optional[Dict[str, float]] = None
    ) -> List[StrategySignal]:
        """Generate MA crossover signals."""
        signals = []
        
        for symbol, df in data.items():
            if 'close' not in df.columns:
                continue
            
            prices = df['close']
            
            if len(prices) < self.slow_period:
                continue
            
            fast_ma = prices.rolling(self.fast_period).mean().iloc[-1]
            slow_ma = prices.rolling(self.slow_period).mean().iloc[-1]
            
            # Check for crossover
            fast_prev = prices.rolling(self.fast_period).mean().iloc[-2]
            slow_prev = prices.rolling(self.slow_period).mean().iloc[-2]
            
            if fast_ma > slow_ma and fast_prev <= slow_prev:
                # Golden cross
                signals.append(StrategySignal(
                    symbol=symbol,
                    action='buy',
                    weight=1.0 / len(data),
                    reason="Golden Cross (50 > 200)"
                ))
            elif fast_ma < slow_ma and fast_prev >= slow_prev:
                # Death cross
                signals.append(StrategySignal(
                    symbol=symbol,
                    action='sell',
                    weight=0.0,
                    reason="Death Cross (50 < 200)"
                ))
            elif fast_ma > slow_ma:
                signals.append(StrategySignal(
                    symbol=symbol,
                    action='hold',
                    weight=current_positions.get(symbol, 0) if current_positions else 1.0 / len(data),
                    reason="Uptrend (50 > 200)"
                ))
            else:
                signals.append(StrategySignal(
                    symbol=symbol,
                    action='hold',
                    weight=0.0,
                    reason="Downtrend (50 < 200)"
                ))
        
        return signals
