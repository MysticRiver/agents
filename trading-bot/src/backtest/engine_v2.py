"""
Backtesting engine V2 - with corrected stop/target logic

Key fixes:
1. Signals on bar N filled at bar N+1 Open (no look-ahead)
2. Stop/target anchored to ACTUAL entry price, not signal bar price
3. Conservative: if both stop and target could hit same bar, assume stop hits first
"""
import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
from loguru import logger

from .metrics import calculate_metrics, PerformanceMetrics


class OrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"


class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"


@dataclass
class Trade:
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
    holding_period: int
    exit_reason: str = ""


@dataclass
class BacktestResult:
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


class BacktestEngineV2:
    """
    Backtest engine with corrected stop/target logic.
    """
    
    TICK_SIZE = 0.25
    TICK_VALUE = 0.50
    POINT_VALUE = 2.00  # MNQ
    
    def __init__(
        self,
        initial_capital: float = 25000.0,
        commission_per_contract: float = 0.50,
        slippage_ticks: float = 1.0,
        max_position_size: int = 5,
        margin_per_contract: float = 500.0,
        use_stops: bool = True,
        stop_atr_mult: float = 1.5,
        target_atr_mult: float = 3.0
    ):
        self.initial_capital = initial_capital
        self.commission_per_contract = commission_per_contract
        self.slippage_ticks = slippage_ticks
        self.max_position_size = max_position_size
        self.margin_per_contract = margin_per_contract
        self.use_stops = use_stops
        self.stop_atr_mult = stop_atr_mult
        self.target_atr_mult = target_atr_mult
        
        self._reset()
    
    def _reset(self):
        self.capital = self.initial_capital
        self.position = 0
        self.entry_price = 0.0
        self.entry_time = None
        self.entry_bar_idx = 0
        self.entry_side = None
        self.entry_commission = 0.0
        self.stop_price = None
        self.target_price = None
        self.trades: List[Trade] = []
        self.equity_history: List[float] = []
    
    def run(
        self,
        data: pd.DataFrame,
        strategy,
        verbose: bool = False
    ) -> BacktestResult:
        """Run backtest with corrected stop/target handling."""
        self._reset()
        
        signals_df = strategy.generate_signals(data)
        
        logger.info(f"Running backtest for {strategy.name}")
        logger.info(f"Data range: {data.index[0]} to {data.index[-1]}")
        logger.info(f"Initial capital: ${self.initial_capital:,.2f}")
        logger.info(f"Stops enabled: {self.use_stops}")
        
        pending_signal = 0
        pending_atr = 0.0
        
        for i in range(len(signals_df)):
            bar = signals_df.iloc[i]
            timestamp = signals_df.index[i]
            
            open_price = bar["Open"]
            high_price = bar["High"]
            low_price = bar["Low"]
            close_price = bar["Close"]
            atr = bar.get("ATR", 100.0)  # Default ATR if not present
            
            # Process pending signal at this bar's Open
            if pending_signal != 0:
                self._process_entry(pending_signal, open_price, pending_atr, timestamp, i, verbose)
                pending_signal = 0
            
            # Check stop/target using this bar's High/Low
            if self.position != 0 and self.use_stops:
                self._check_exits(high_price, low_price, timestamp, i, verbose)
            
            # Update equity
            unrealized = 0.0
            if self.position != 0:
                if self.position > 0:
                    unrealized = (close_price - self.entry_price) * self.POINT_VALUE * abs(self.position)
                else:
                    unrealized = (self.entry_price - close_price) * self.POINT_VALUE * abs(self.position)
            self.equity_history.append(self.capital + unrealized)
            
            # Get new signal for next bar
            signal = bar.get("Signal", 0)
            if signal != 0 and signal != self.position:  # Only if different from current position
                pending_signal = signal
                pending_atr = atr
        
        # Close remaining position
        if self.position != 0:
            self._close_position(
                signals_df.iloc[-1]["Close"],
                signals_df.index[-1],
                len(signals_df) - 1,
                "end_of_data",
                verbose
            )
        
        # Calculate metrics
        equity_curve = pd.Series(self.equity_history, index=signals_df.index[:len(self.equity_history)])
        data_frequency = self._infer_frequency(signals_df.index)
        
        metrics = calculate_metrics(
            equity_curve=equity_curve,
            trades=self.trades,
            initial_capital=self.initial_capital,
            data_frequency=data_frequency
        )
        
        drawdown_curve = self._calculate_drawdown(equity_curve)
        
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
                   f"Return: {result.total_return_pct:.2f}%, Sharpe: {metrics.sharpe_ratio:.2f}")
        
        return result
    
    def _process_entry(
        self,
        signal: int,
        price: float,
        atr: float,
        timestamp,
        bar_idx: int,
        verbose: bool
    ):
        """Process entry signal."""
        slippage = self.slippage_ticks * self.TICK_SIZE
        
        # Close existing position if reversing
        if self.position != 0 and signal != self.position:
            self._close_position(price, timestamp, bar_idx, "signal_reversal", verbose)
        
        # Calculate fill price with slippage
        if signal == 1:  # Buy
            fill_price = price + slippage
        else:  # Sell
            fill_price = price - slippage
        
        # Check margin
        if self.capital < self.margin_per_contract:
            if verbose:
                logger.warning(f"Insufficient margin at {timestamp}")
            return
        
        # Deduct commission
        commission = self.commission_per_contract
        self.capital -= commission
        
        # Set position
        self.position = signal  # +1 or -1
        self.entry_price = fill_price
        self.entry_time = timestamp
        self.entry_bar_idx = bar_idx
        self.entry_side = OrderSide.BUY if signal == 1 else OrderSide.SELL
        self.entry_commission = commission
        
        # Set stop and target based on ENTRY price
        if self.use_stops:
            if signal == 1:  # Long
                self.stop_price = fill_price - (atr * self.stop_atr_mult)
                self.target_price = fill_price + (atr * self.target_atr_mult)
            else:  # Short
                self.stop_price = fill_price + (atr * self.stop_atr_mult)
                self.target_price = fill_price - (atr * self.target_atr_mult)
        
        if verbose:
            logger.info(f"OPEN {self.entry_side.value.upper()} @ {fill_price:.2f}")
            if self.use_stops:
                logger.info(f"  Stop: {self.stop_price:.2f}, Target: {self.target_price:.2f}")
    
    def _check_exits(
        self,
        high: float,
        low: float,
        timestamp,
        bar_idx: int,
        verbose: bool
    ):
        """Check stop and target exits using High/Low."""
        if self.position == 0:
            return
        
        stop_hit = False
        target_hit = False
        
        if self.position > 0:  # Long
            stop_hit = low <= self.stop_price
            target_hit = high >= self.target_price
        else:  # Short
            stop_hit = high >= self.stop_price
            target_hit = low <= self.target_price
        
        # Conservative: if both could hit, assume stop hits first
        if stop_hit:
            self._close_position(self.stop_price, timestamp, bar_idx, "stop_loss", verbose)
        elif target_hit:
            self._close_position(self.target_price, timestamp, bar_idx, "take_profit", verbose)
    
    def _close_position(
        self,
        price: float,
        timestamp,
        bar_idx: int,
        reason: str,
        verbose: bool
    ):
        """Close current position."""
        if self.position == 0:
            return
        
        slippage = self.slippage_ticks * self.TICK_SIZE
        
        # Apply slippage for exit (unfavorable)
        if self.position > 0:  # Closing long = selling
            fill_price = price - slippage
            pnl_points = fill_price - self.entry_price
        else:  # Closing short = buying
            fill_price = price + slippage
            pnl_points = self.entry_price - fill_price
        
        pnl = pnl_points * self.POINT_VALUE * abs(self.position)
        
        # Deduct exit commission
        commission = self.commission_per_contract
        pnl -= commission
        
        self.capital += pnl
        
        trade = Trade(
            entry_time=self.entry_time,
            exit_time=timestamp,
            side=self.entry_side,
            quantity=abs(self.position),
            entry_price=self.entry_price,
            exit_price=fill_price,
            pnl=pnl,
            pnl_pct=(pnl / self.initial_capital) * 100,
            commission=self.entry_commission + commission,
            slippage=slippage * 2 * self.POINT_VALUE,
            holding_period=bar_idx - self.entry_bar_idx,
            exit_reason=reason
        )
        self.trades.append(trade)
        
        if verbose:
            logger.info(f"CLOSE {self.entry_side.value.upper()} @ {fill_price:.2f} "
                       f"P&L: ${pnl:.2f} ({reason})")
        
        # Reset
        self.position = 0
        self.entry_price = 0.0
        self.stop_price = None
        self.target_price = None
    
    @staticmethod
    def _calculate_drawdown(equity_curve: pd.Series) -> pd.Series:
        rolling_max = equity_curve.expanding().max()
        return (equity_curve - rolling_max) / rolling_max * 100
    
    @staticmethod
    def _infer_frequency(index: pd.DatetimeIndex) -> str:
        if len(index) < 2:
            return "1h"
        diffs = pd.Series(index).diff().dropna()
        minutes = diffs.median().total_seconds() / 60
        if minutes <= 7:
            return "5m"
        elif minutes <= 90:
            return "1h"
        return "1d"
