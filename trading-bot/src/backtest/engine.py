"""Backtesting engine for futures trading strategies"""
import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Callable
from datetime import datetime
from enum import Enum
from loguru import logger

from .metrics import calculate_metrics, PerformanceMetrics


class OrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"


@dataclass
class Order:
    """Represents a trading order"""
    side: OrderSide
    quantity: int
    order_type: OrderType = OrderType.MARKET
    price: Optional[float] = None
    stop_price: Optional[float] = None
    timestamp: Optional[datetime] = None
    filled: bool = False
    fill_price: Optional[float] = None
    fill_timestamp: Optional[datetime] = None
    order_id: Optional[str] = None


@dataclass
class Position:
    """Represents a position"""
    quantity: int = 0
    avg_price: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0


@dataclass
class Trade:
    """Represents a completed trade"""
    entry_time: datetime
    exit_time: datetime
    side: OrderSide
    quantity: int
    entry_price: float
    exit_price: float
    pnl: float
    pnl_pct: float
    commission: float
    slippage: float
    holding_period: int  # in bars


@dataclass
class BacktestResult:
    """Results from a backtest run"""
    strategy_name: str
    start_date: datetime
    end_date: datetime
    initial_capital: float
    final_capital: float
    total_return: float
    total_return_pct: float
    metrics: PerformanceMetrics
    trades: List[Trade]
    equity_curve: pd.Series
    drawdown_curve: pd.Series
    signals: pd.DataFrame
    parameters: Dict[str, Any]
    
    def __repr__(self) -> str:
        return (
            f"BacktestResult({self.strategy_name})\n"
            f"  Period: {self.start_date.date()} to {self.end_date.date()}\n"
            f"  Return: {self.total_return_pct:.2f}%\n"
            f"  Sharpe: {self.metrics.sharpe_ratio:.2f}\n"
            f"  Max DD: {self.metrics.max_drawdown_pct:.2f}%\n"
            f"  Trades: {self.metrics.total_trades}"
        )


class BacktestEngine:
    """
    Event-driven backtesting engine for futures trading.
    
    Features:
    - Realistic commission and slippage modeling
    - Position tracking with unrealized P&L
    - Detailed trade logging
    - Performance metrics calculation
    """
    
    # MNQ Contract Specifications
    TICK_SIZE = 0.25
    TICK_VALUE = 0.50  # $0.50 per tick
    POINT_VALUE = 2.00  # $2.00 per point (1 point = 4 ticks)
    
    def __init__(
        self,
        initial_capital: float = 10000.0,
        commission_per_contract: float = 0.50,  # Round trip
        slippage_ticks: float = 1.0,  # Average slippage in ticks
        max_position_size: int = 5,
        margin_per_contract: float = 1500.0
    ):
        self.initial_capital = initial_capital
        self.commission_per_contract = commission_per_contract
        self.slippage_ticks = slippage_ticks
        self.max_position_size = max_position_size
        self.margin_per_contract = margin_per_contract
        
        self._reset()
        
    def _reset(self):
        """Reset engine state"""
        self.capital = self.initial_capital
        self.position = Position()
        self.trades: List[Trade] = []
        self.equity_history: List[float] = []
        self.pending_orders: List[Order] = []
        self._current_bar = None
        self._entry_bar_idx = None
        self._entry_price = None
        self._entry_side = None
        
    def run(
        self,
        data: pd.DataFrame,
        strategy: "BaseStrategy",
        verbose: bool = False
    ) -> BacktestResult:
        """
        Run backtest on historical data.
        
        IMPORTANT: Signals generated on bar N are executed at bar N+1's Open
        to avoid look-ahead bias. A signal on bar N's Close cannot be filled
        until the next bar opens.
        
        Args:
            data: DataFrame with OHLCV data and indicators
            strategy: Strategy instance with generate_signals method
            verbose: Print trade details
        """
        self._reset()
        
        # Generate signals
        signals_df = strategy.generate_signals(data)
        
        logger.info(f"Running backtest for {strategy.name}")
        logger.info(f"Data range: {data.index[0]} to {data.index[-1]}")
        logger.info(f"Initial capital: ${self.initial_capital:,.2f}")
        
        # Track pending signal from previous bar
        pending_signal = 0
        
        # Main backtest loop
        for i in range(len(signals_df)):
            self._current_bar = signals_df.iloc[i]
            bar_idx = i
            timestamp = signals_df.index[i]
            
            # Use Open price for fills (signal from bar N-1, fill at bar N Open)
            fill_price = self._current_bar["Open"]
            current_price = self._current_bar["Close"]
            
            # Process pending signal from PREVIOUS bar at THIS bar's Open
            if pending_signal != 0:
                self._process_signal(pending_signal, fill_price, timestamp, bar_idx, verbose)
                pending_signal = 0
            
            # Update unrealized P&L using current close
            if self.position.quantity != 0:
                self._update_unrealized_pnl(current_price)
            
            # Record equity at bar close
            equity = self.capital + self.position.unrealized_pnl
            self.equity_history.append(equity)
            
            # Get signal for THIS bar - will be executed at NEXT bar's Open
            signal = self._current_bar.get("Signal", 0)
            if signal != 0:
                pending_signal = signal
            
            # NOTE: Stop/target exits disabled for pure signal-based backtest
            # The stop/target levels in strategies are based on signal bar data,
            # not entry bar data, which creates bias. Use signals only for exits.
        
        # Close any remaining position at end (at last bar's Close)
        if self.position.quantity != 0:
            final_price = signals_df.iloc[-1]["Close"]
            self._close_position(final_price, signals_df.index[-1], len(signals_df) - 1, "end_of_backtest", verbose)
        
        # Handle pending signal that couldn't be executed (end of data)
        if pending_signal != 0 and verbose:
            logger.info(f"Pending signal {pending_signal} not executed (end of data)")
        
        # Calculate final results
        equity_curve = pd.Series(self.equity_history, index=signals_df.index[:len(self.equity_history)])
        drawdown_curve = self._calculate_drawdown(equity_curve)
        
        # Determine data frequency from index
        data_frequency = self._infer_data_frequency(signals_df.index)
        
        metrics = calculate_metrics(
            equity_curve=equity_curve,
            trades=self.trades,
            initial_capital=self.initial_capital,
            risk_free_rate=0.05,
            data_frequency=data_frequency
        )
        
        result = BacktestResult(
            strategy_name=strategy.name,
            start_date=signals_df.index[0].to_pydatetime(),
            end_date=signals_df.index[-1].to_pydatetime(),
            initial_capital=self.initial_capital,
            final_capital=self.capital,
            total_return=self.capital - self.initial_capital,
            total_return_pct=((self.capital - self.initial_capital) / self.initial_capital) * 100,
            metrics=metrics,
            trades=self.trades,
            equity_curve=equity_curve,
            drawdown_curve=drawdown_curve,
            signals=signals_df,
            parameters=strategy.parameters
        )
        
        logger.info(f"Backtest complete: {len(self.trades)} trades, "
                   f"Return: {result.total_return_pct:.2f}%, "
                   f"Sharpe: {metrics.sharpe_ratio:.2f}")
        
        return result
    
    def _process_signal(
        self, 
        signal: int, 
        price: float, 
        timestamp: datetime,
        bar_idx: int,
        verbose: bool
    ):
        """Process trading signal"""
        # signal: 1 = buy, -1 = sell, 0 = hold
        
        current_pos = self.position.quantity
        
        if signal == 1:  # Buy signal
            if current_pos < 0:  # Close short first
                self._close_position(price, timestamp, bar_idx, "signal", verbose)
            if current_pos <= 0:  # Open long
                self._open_position(OrderSide.BUY, 1, price, timestamp, bar_idx, verbose)
                
        elif signal == -1:  # Sell signal
            if current_pos > 0:  # Close long first
                self._close_position(price, timestamp, bar_idx, "signal", verbose)
            if current_pos >= 0:  # Open short
                self._open_position(OrderSide.SELL, 1, price, timestamp, bar_idx, verbose)
    
    def _open_position(
        self,
        side: OrderSide,
        quantity: int,
        price: float,
        timestamp: datetime,
        bar_idx: int,
        verbose: bool
    ):
        """Open a new position"""
        # Apply slippage
        slippage = self.slippage_ticks * self.TICK_SIZE
        if side == OrderSide.BUY:
            fill_price = price + slippage
        else:
            fill_price = price - slippage
        
        # Check margin - need positive capital and sufficient margin
        required_margin = quantity * self.margin_per_contract
        if self.capital <= 0 or required_margin > self.capital:
            if verbose:
                logger.warning(f"Insufficient margin: need ${required_margin:.2f}, have ${self.capital:.2f}")
            return
        
        # Apply commission
        commission = self.commission_per_contract * quantity
        self.capital -= commission
        
        # Update position
        if side == OrderSide.BUY:
            self.position.quantity = quantity
        else:
            self.position.quantity = -quantity
            
        self.position.avg_price = fill_price
        
        # Record entry
        self._entry_price = fill_price
        self._entry_bar_idx = bar_idx
        self._entry_side = side
        self._entry_time = timestamp
        self._entry_commission = commission
        
        if verbose:
            logger.info(f"OPEN {side.value.upper()} {quantity} @ {fill_price:.2f} "
                       f"(commission: ${commission:.2f})")
    
    def _close_position(
        self,
        price: float,
        timestamp: datetime,
        bar_idx: int,
        reason: str,
        verbose: bool
    ):
        """Close current position"""
        if self.position.quantity == 0:
            return
            
        quantity = abs(self.position.quantity)
        side = OrderSide.SELL if self.position.quantity > 0 else OrderSide.BUY
        
        # Apply slippage
        slippage = self.slippage_ticks * self.TICK_SIZE
        if side == OrderSide.BUY:
            fill_price = price + slippage
        else:
            fill_price = price - slippage
        
        # Calculate P&L
        if self.position.quantity > 0:  # Was long
            pnl_points = fill_price - self.position.avg_price
        else:  # Was short
            pnl_points = self.position.avg_price - fill_price
            
        pnl = pnl_points * self.POINT_VALUE * quantity
        
        # Apply commission
        commission = self.commission_per_contract * quantity
        pnl -= commission
        
        # Update capital
        self.capital += pnl
        
        # Record trade
        trade = Trade(
            entry_time=self._entry_time,
            exit_time=timestamp,
            side=self._entry_side,
            quantity=quantity,
            entry_price=self._entry_price,
            exit_price=fill_price,
            pnl=pnl,
            pnl_pct=(pnl / self.initial_capital) * 100,
            commission=self._entry_commission + commission,
            slippage=slippage * 2 * self.POINT_VALUE * quantity,
            holding_period=bar_idx - self._entry_bar_idx
        )
        self.trades.append(trade)
        
        if verbose:
            logger.info(f"CLOSE {self._entry_side.value.upper()} {quantity} @ {fill_price:.2f} "
                       f"P&L: ${pnl:.2f} ({reason})")
        
        # Reset position
        self.position = Position()
        self._entry_price = None
        self._entry_bar_idx = None
        self._entry_side = None
    
    def _check_exit_conditions_intrabar(
        self,
        timestamp: datetime,
        bar_idx: int,
        verbose: bool
    ):
        """
        Check for stop loss / take profit conditions using High/Low.
        
        Conservative assumption: if both stop and target hit on same bar,
        assume stop was hit first (worst case).
        """
        if not hasattr(self._current_bar, "StopLoss") or not hasattr(self._current_bar, "TakeProfit"):
            return
            
        stop_loss = self._current_bar.get("StopLoss")
        take_profit = self._current_bar.get("TakeProfit")
        
        if pd.isna(stop_loss) or pd.isna(take_profit):
            return
        
        high = self._current_bar["High"]
        low = self._current_bar["Low"]
        
        if self.position.quantity > 0:  # Long position
            stop_hit = low <= stop_loss
            target_hit = high >= take_profit
            
            if stop_hit and target_hit:
                # Both hit - assume stop first (conservative)
                self._close_position(stop_loss, timestamp, bar_idx, "stop_loss", verbose)
            elif stop_hit:
                self._close_position(stop_loss, timestamp, bar_idx, "stop_loss", verbose)
            elif target_hit:
                self._close_position(take_profit, timestamp, bar_idx, "take_profit", verbose)
                
        elif self.position.quantity < 0:  # Short position
            stop_hit = high >= stop_loss
            target_hit = low <= take_profit
            
            if stop_hit and target_hit:
                # Both hit - assume stop first (conservative)
                self._close_position(stop_loss, timestamp, bar_idx, "stop_loss", verbose)
            elif stop_hit:
                self._close_position(stop_loss, timestamp, bar_idx, "stop_loss", verbose)
            elif target_hit:
                self._close_position(take_profit, timestamp, bar_idx, "take_profit", verbose)
    
    def _update_unrealized_pnl(self, current_price: float):
        """Update unrealized P&L for current position"""
        if self.position.quantity > 0:
            pnl_points = current_price - self.position.avg_price
        else:
            pnl_points = self.position.avg_price - current_price
            
        self.position.unrealized_pnl = pnl_points * self.POINT_VALUE * abs(self.position.quantity)
    
    @staticmethod
    def _calculate_drawdown(equity_curve: pd.Series) -> pd.Series:
        """Calculate drawdown series"""
        rolling_max = equity_curve.expanding().max()
        drawdown = (equity_curve - rolling_max) / rolling_max * 100
        return drawdown
    
    @staticmethod
    def _infer_data_frequency(index: pd.DatetimeIndex) -> str:
        """Infer data frequency from datetime index"""
        if len(index) < 2:
            return "1h"
        
        # Get median time difference
        diffs = pd.Series(index).diff().dropna()
        median_diff = diffs.median()
        
        # Map to frequency string
        minutes = median_diff.total_seconds() / 60
        
        if minutes <= 1.5:
            return "1m"
        elif minutes <= 7:
            return "5m"
        elif minutes <= 20:
            return "15m"
        elif minutes <= 90:
            return "1h"
        elif minutes <= 60 * 24:
            return "1d"
        else:
            return "1d"
