"""Risk management for trading operations"""
import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from typing import Optional, List, Dict
from enum import Enum
from loguru import logger


class TradingRestriction(Enum):
    """Reasons for restricting trading"""
    DAILY_LOSS_LIMIT = "daily_loss_limit"
    MAX_POSITION = "max_position"
    NEWS_BLACKOUT = "news_blackout"
    SESSION_CLOSED = "session_closed"
    DRAWDOWN_LIMIT = "drawdown_limit"
    MAX_TRADES = "max_trades_reached"
    VOLATILITY_SPIKE = "volatility_spike"


@dataclass
class RiskConfig:
    """Risk management configuration"""
    # Position sizing
    max_position_size: int = 3  # Max contracts
    risk_per_trade_pct: float = 1.0  # % of account to risk per trade
    
    # Daily limits
    max_daily_loss: float = 500.0  # Max daily loss in $
    max_daily_loss_pct: float = 5.0  # Max daily loss as % of account
    max_trades_per_day: int = 10
    
    # Drawdown limits
    max_drawdown_pct: float = 20.0  # Max drawdown before stopping
    drawdown_cooldown_hours: int = 24  # Hours to wait after hitting DD limit
    
    # Session restrictions
    trading_start_time: time = field(default_factory=lambda: time(9, 30))
    trading_end_time: time = field(default_factory=lambda: time(16, 0))
    close_positions_before_end: int = 15  # Minutes before session end
    
    # News avoidance
    news_blackout_minutes: int = 30  # Minutes before/after major news
    
    # Volatility limits
    max_atr_multiplier: float = 3.0  # Max ATR vs 20-day average
    
    # Contract specifications (MNQ)
    tick_size: float = 0.25
    tick_value: float = 0.50
    point_value: float = 2.00
    margin_per_contract: float = 1500.0


class RiskManager:
    """
    Risk manager for futures trading.
    
    Handles position sizing, daily limits, and trading restrictions.
    """
    
    def __init__(self, config: Optional[RiskConfig] = None):
        self.config = config or RiskConfig()
        
        # Daily tracking
        self._daily_pnl: float = 0.0
        self._daily_trades: int = 0
        self._last_reset_date: Optional[datetime] = None
        
        # Position tracking
        self._current_position: int = 0
        self._peak_equity: float = 0.0
        self._starting_equity: float = 0.0
        
        # Restrictions
        self._active_restrictions: List[TradingRestriction] = []
        self._drawdown_cooldown_until: Optional[datetime] = None
        
        # News events (can be populated externally)
        self._news_events: List[datetime] = []
        
    def initialize(self, account_equity: float):
        """Initialize risk manager with account equity"""
        self._starting_equity = account_equity
        self._peak_equity = account_equity
        self._reset_daily_stats()
        logger.info(f"Risk manager initialized with ${account_equity:,.2f}")
        
    def _reset_daily_stats(self):
        """Reset daily statistics"""
        self._daily_pnl = 0.0
        self._daily_trades = 0
        self._last_reset_date = datetime.now().date()
        self._active_restrictions = [
            r for r in self._active_restrictions 
            if r not in [TradingRestriction.DAILY_LOSS_LIMIT, TradingRestriction.MAX_TRADES]
        ]
        logger.info("Daily stats reset")
        
    def check_new_day(self, current_time: datetime):
        """Check if we need to reset daily stats"""
        if self._last_reset_date is None or current_time.date() > self._last_reset_date:
            self._reset_daily_stats()
            
    def can_trade(self, current_time: datetime, current_price: float, atr: Optional[float] = None) -> tuple:
        """
        Check if trading is allowed.
        
        Returns:
            (can_trade: bool, reason: Optional[TradingRestriction])
        """
        self.check_new_day(current_time)
        
        # Check drawdown cooldown
        if self._drawdown_cooldown_until and current_time < self._drawdown_cooldown_until:
            return False, TradingRestriction.DRAWDOWN_LIMIT
        
        # Check session time
        current_time_only = current_time.time()
        if current_time_only < self.config.trading_start_time:
            return False, TradingRestriction.SESSION_CLOSED
        
        close_cutoff = (
            datetime.combine(datetime.today(), self.config.trading_end_time) -
            timedelta(minutes=self.config.close_positions_before_end)
        ).time()
        
        if current_time_only > close_cutoff:
            return False, TradingRestriction.SESSION_CLOSED
        
        # Check daily loss limit
        daily_loss_limit = min(
            self.config.max_daily_loss,
            self._starting_equity * (self.config.max_daily_loss_pct / 100)
        )
        if self._daily_pnl <= -daily_loss_limit:
            return False, TradingRestriction.DAILY_LOSS_LIMIT
        
        # Check daily trade limit
        if self._daily_trades >= self.config.max_trades_per_day:
            return False, TradingRestriction.MAX_TRADES
        
        # Check news blackout
        for news_time in self._news_events:
            blackout_start = news_time - timedelta(minutes=self.config.news_blackout_minutes)
            blackout_end = news_time + timedelta(minutes=self.config.news_blackout_minutes)
            if blackout_start <= current_time <= blackout_end:
                return False, TradingRestriction.NEWS_BLACKOUT
        
        # Check volatility
        if atr is not None:
            # Compare to historical ATR
            pass  # Would need historical data
        
        return True, None
    
    def calculate_position_size(
        self,
        account_equity: float,
        entry_price: float,
        stop_loss: float,
        signal_direction: int  # 1 for long, -1 for short
    ) -> int:
        """
        Calculate position size based on risk parameters.
        
        Uses fixed fractional position sizing.
        """
        if account_equity <= 0:
            return 0
            
        # Calculate risk amount
        risk_amount = account_equity * (self.config.risk_per_trade_pct / 100)
        
        # Calculate stop distance in points
        if signal_direction == 1:  # Long
            stop_distance = entry_price - stop_loss
        else:  # Short
            stop_distance = stop_loss - entry_price
            
        if stop_distance <= 0:
            logger.warning("Invalid stop loss - stop distance <= 0")
            return 0
        
        # Calculate risk per contract
        risk_per_contract = stop_distance * self.config.point_value
        
        # Calculate position size
        position_size = int(risk_amount / risk_per_contract)
        
        # Apply maximum limits
        position_size = min(position_size, self.config.max_position_size)
        
        # Check margin requirements
        required_margin = position_size * self.config.margin_per_contract
        if required_margin > account_equity * 0.5:  # Use max 50% of account for margin
            position_size = int((account_equity * 0.5) / self.config.margin_per_contract)
        
        # Ensure at least 1 contract if we have margin
        if position_size == 0 and account_equity >= self.config.margin_per_contract:
            position_size = 1
            
        return max(0, position_size)
    
    def record_trade(self, pnl: float, contracts: int):
        """Record a completed trade"""
        self._daily_pnl += pnl
        self._daily_trades += 1
        
        logger.info(f"Trade recorded: P&L=${pnl:.2f}, "
                   f"Daily P&L=${self._daily_pnl:.2f}, "
                   f"Trades today={self._daily_trades}")
        
    def update_equity(self, current_equity: float, current_time: datetime):
        """Update equity tracking for drawdown calculations"""
        # Update peak
        if current_equity > self._peak_equity:
            self._peak_equity = current_equity
        
        # Calculate drawdown
        drawdown_pct = (self._peak_equity - current_equity) / self._peak_equity * 100
        
        # Check drawdown limit
        if drawdown_pct >= self.config.max_drawdown_pct:
            logger.warning(f"Max drawdown reached: {drawdown_pct:.2f}%")
            self._drawdown_cooldown_until = current_time + timedelta(
                hours=self.config.drawdown_cooldown_hours
            )
            if TradingRestriction.DRAWDOWN_LIMIT not in self._active_restrictions:
                self._active_restrictions.append(TradingRestriction.DRAWDOWN_LIMIT)
                
        return drawdown_pct
    
    def add_news_event(self, event_time: datetime):
        """Add a news event for blackout period"""
        self._news_events.append(event_time)
        self._news_events.sort()
        
    def clear_news_events(self):
        """Clear all news events"""
        self._news_events.clear()
        
    def set_position(self, contracts: int):
        """Update current position"""
        self._current_position = contracts
        
    def get_position(self) -> int:
        """Get current position"""
        return self._current_position
    
    def should_close_position(self, current_time: datetime) -> tuple:
        """Check if we should close position before session end"""
        current_time_only = current_time.time()
        
        close_cutoff = (
            datetime.combine(datetime.today(), self.config.trading_end_time) -
            timedelta(minutes=self.config.close_positions_before_end)
        ).time()
        
        if current_time_only >= close_cutoff and self._current_position != 0:
            return True, "session_end"
            
        return False, None
    
    def get_stats(self) -> Dict:
        """Get current risk stats"""
        return {
            "daily_pnl": self._daily_pnl,
            "daily_trades": self._daily_trades,
            "current_position": self._current_position,
            "peak_equity": self._peak_equity,
            "active_restrictions": [r.value for r in self._active_restrictions],
            "drawdown_cooldown_until": self._drawdown_cooldown_until
        }
        
    def calculate_kelly_position(
        self,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
        account_equity: float,
        kelly_fraction: float = 0.5
    ) -> int:
        """
        Calculate position size using Kelly Criterion.
        
        kelly_fraction: Use half-Kelly for more conservative sizing
        """
        if avg_loss == 0 or account_equity <= 0:
            return 0
            
        win_prob = win_rate / 100
        loss_prob = 1 - win_prob
        
        # Kelly formula: f* = (bp - q) / b
        # where b = avg_win/avg_loss, p = win_prob, q = loss_prob
        b = abs(avg_win / avg_loss)
        
        kelly_pct = (b * win_prob - loss_prob) / b
        
        if kelly_pct <= 0:
            return 0
            
        # Apply fraction (half-Kelly recommended)
        kelly_pct *= kelly_fraction
        
        # Calculate dollar risk
        risk_amount = account_equity * kelly_pct
        
        # Convert to contracts (assuming avg risk per contract)
        avg_risk_per_contract = abs(avg_loss) if avg_loss != 0 else self.config.margin_per_contract
        position_size = int(risk_amount / avg_risk_per_contract)
        
        # Apply maximum
        return min(position_size, self.config.max_position_size)
