"""
Backtesting engine with memory system integration.

Extends BacktestEngineV2 with:
- Trade ledger logging
- Learnings file generation
- Memory gate for signal filtering

This allows testing the course's memory system in backtests.
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from datetime import datetime
from pathlib import Path
import tempfile
import os

from .engine_v2 import BacktestEngineV2, BacktestResult, Trade, OrderSide
from .metrics import calculate_metrics
from ..memory import TradeLedger, LearningsFile, MemoryGate, PostTradeReviewer
from ..memory.post_trade_review import TradeDetails


@dataclass
class MemoryBacktestResult(BacktestResult):
    """Extended result with memory system stats."""
    signals_skipped: int = 0
    signals_executed: int = 0
    lessons_written: int = 0
    memory_gate_enabled: bool = True


class BacktestEngineWithMemory(BacktestEngineV2):
    """
    Backtest engine with memory system integration.
    
    Tests the course's learning loop:
    1. Log all signals to trade ledger
    2. Check memory gate before entry
    3. Generate lessons after losses
    """
    
    def __init__(
        self,
        initial_capital: float = 25000.0,
        commission_per_contract: float = 0.50,
        slippage_ticks: float = 1.0,
        max_position_size: int = 5,
        margin_per_contract: float = 500.0,
        use_stops: bool = True,
        stop_atr_mult: float = 1.5,
        target_atr_mult: float = 3.0,
        memory_enabled: bool = True,
        memory_window_hours: float = 24.0,
        ledger_path: Optional[str] = None,
        learnings_path: Optional[str] = None
    ):
        super().__init__(
            initial_capital=initial_capital,
            commission_per_contract=commission_per_contract,
            slippage_ticks=slippage_ticks,
            max_position_size=max_position_size,
            margin_per_contract=margin_per_contract,
            use_stops=use_stops,
            stop_atr_mult=stop_atr_mult,
            target_atr_mult=target_atr_mult
        )
        
        self.memory_enabled = memory_enabled
        self.memory_window_hours = memory_window_hours
        
        # Use temp files if paths not provided
        self._temp_dir = None
        if ledger_path is None or learnings_path is None:
            self._temp_dir = tempfile.mkdtemp()
        
        self.ledger_path = ledger_path or os.path.join(self._temp_dir, "trade_ledger.csv")
        self.learnings_path = learnings_path or os.path.join(self._temp_dir, "learnings.txt")
        
        # Initialize memory components
        self.ledger = TradeLedger(self.ledger_path)
        self.learnings = LearningsFile(self.learnings_path)
        self.memory_gate = MemoryGate(
            self.learnings,
            enabled=memory_enabled,
            window_hours=memory_window_hours
        )
        self.reviewer = PostTradeReviewer(use_llm=False)  # Dry-run mode
        
        # Stats
        self.signals_skipped = 0
        self.signals_executed = 0
        self.lessons_written = 0
    
    def _reset(self):
        """Reset engine state."""
        super()._reset()
        self.signals_skipped = 0
        self.signals_executed = 0
        self.lessons_written = 0
        
        # Clear memory files for fresh backtest
        if hasattr(self, 'ledger'):
            self.ledger.clear()
        if hasattr(self, 'learnings'):
            self.learnings.clear()
    
    def run(
        self,
        data: pd.DataFrame,
        strategy,
        verbose: bool = False
    ) -> MemoryBacktestResult:
        """Run backtest with memory system."""
        self._reset()
        
        signals_df = strategy.generate_signals(data)
        strategy_name = strategy.name
        
        if verbose:
            print(f"Running backtest for {strategy_name}")
            print(f"Memory gate: {'ON' if self.memory_enabled else 'OFF'}")
            print(f"Memory window: {self.memory_window_hours} hours")
        
        pending_signal = 0
        pending_atr = 0.0
        pending_time = None
        
        for i in range(len(signals_df)):
            bar = signals_df.iloc[i]
            timestamp = signals_df.index[i]
            
            open_price = bar["Open"]
            high_price = bar["High"]
            low_price = bar["Low"]
            close_price = bar["Close"]
            atr = bar.get("ATR", 100.0)
            
            # Process pending signal at this bar's Open
            if pending_signal != 0:
                direction = "LONG" if pending_signal == 1 else "SHORT"
                setup_id = f"{strategy_name}_{direction}_{pending_time}"
                
                # Check memory gate
                should_skip, skip_reason = self.memory_gate.should_skip(
                    strategy=strategy_name,
                    direction=direction
                )
                
                if should_skip:
                    self.signals_skipped += 1
                    self.ledger.log_signal(
                        action="SKIP",
                        setup_id=setup_id,
                        strategy=strategy_name,
                        direction=direction,
                        avoided_by_memory=True,
                        skip_reason=skip_reason
                    )
                    if verbose:
                        print(f"SKIP {direction} @ {timestamp}: {skip_reason}")
                else:
                    self.signals_executed += 1
                    self.ledger.log_signal(
                        action="BUY" if pending_signal == 1 else "SELL",
                        setup_id=setup_id,
                        strategy=strategy_name,
                        direction=direction,
                        entry_price=open_price
                    )
                    self._process_entry_with_tracking(
                        pending_signal, open_price, pending_atr, 
                        timestamp, i, setup_id, strategy_name, verbose
                    )
                
                pending_signal = 0
            
            # Check stop/target
            if self.position != 0 and self.use_stops:
                self._check_exits_with_tracking(
                    high_price, low_price, timestamp, i, strategy_name, verbose
                )
            
            # Update equity
            unrealized = 0.0
            if self.position != 0:
                if self.position > 0:
                    unrealized = (close_price - self.entry_price) * self.POINT_VALUE * abs(self.position)
                else:
                    unrealized = (self.entry_price - close_price) * self.POINT_VALUE * abs(self.position)
            self.equity_history.append(self.capital + unrealized)
            
            # Get new signal
            signal = bar.get("Signal", 0)
            if signal != 0 and signal != self.position:
                pending_signal = signal
                pending_atr = atr
                pending_time = timestamp
        
        # Close remaining position
        if self.position != 0:
            self._close_position_with_tracking(
                signals_df.iloc[-1]["Close"],
                signals_df.index[-1],
                len(signals_df) - 1,
                "end_of_data",
                strategy_name,
                verbose
            )
        
        # Calculate metrics
        equity_curve = pd.Series(
            self.equity_history, 
            index=signals_df.index[:len(self.equity_history)]
        )
        data_frequency = self._infer_frequency(signals_df.index)
        
        metrics = calculate_metrics(
            equity_curve=equity_curve,
            trades=self.trades,
            initial_capital=self.initial_capital,
            data_frequency=data_frequency
        )
        
        drawdown_curve = self._calculate_drawdown(equity_curve)
        
        result = MemoryBacktestResult(
            strategy_name=strategy_name,
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
            parameters=strategy.parameters,
            signals_skipped=self.signals_skipped,
            signals_executed=self.signals_executed,
            lessons_written=self.lessons_written,
            memory_gate_enabled=self.memory_enabled
        )
        
        if verbose:
            print(f"\nBacktest complete:")
            print(f"  Trades: {len(self.trades)}")
            print(f"  Signals executed: {self.signals_executed}")
            print(f"  Signals skipped: {self.signals_skipped}")
            print(f"  Lessons written: {self.lessons_written}")
            print(f"  Return: {result.total_return_pct:.2f}%")
        
        return result
    
    def _process_entry_with_tracking(
        self,
        signal: int,
        price: float,
        atr: float,
        timestamp,
        bar_idx: int,
        setup_id: str,
        strategy_name: str,
        verbose: bool
    ):
        """Process entry with ledger tracking."""
        # Close existing position first
        if self.position != 0 and signal != self.position:
            self._close_position_with_tracking(
                price, timestamp, bar_idx, "signal_reversal", strategy_name, verbose
            )
        
        slippage = self.slippage_ticks * self.TICK_SIZE
        
        if signal == 1:
            fill_price = price + slippage
        else:
            fill_price = price - slippage
        
        if self.capital < self.margin_per_contract:
            if verbose:
                print(f"Insufficient margin at {timestamp}")
            return
        
        commission = self.commission_per_contract
        self.capital -= commission
        
        self.position = signal
        self.entry_price = fill_price
        self.entry_time = timestamp
        self.entry_bar_idx = bar_idx
        self.entry_side = OrderSide.BUY if signal == 1 else OrderSide.SELL
        self.entry_commission = commission
        self._current_setup_id = setup_id
        self._current_strategy = strategy_name
        
        if self.use_stops:
            if signal == 1:
                self.stop_price = fill_price - (atr * self.stop_atr_mult)
                self.target_price = fill_price + (atr * self.target_atr_mult)
            else:
                self.stop_price = fill_price + (atr * self.stop_atr_mult)
                self.target_price = fill_price - (atr * self.target_atr_mult)
        
        if verbose:
            direction = "LONG" if signal == 1 else "SHORT"
            print(f"OPEN {direction} @ {fill_price:.2f}")
    
    def _check_exits_with_tracking(
        self,
        high: float,
        low: float,
        timestamp,
        bar_idx: int,
        strategy_name: str,
        verbose: bool
    ):
        """Check exits with tracking."""
        if self.position == 0:
            return
        
        stop_hit = False
        target_hit = False
        
        if self.position > 0:
            stop_hit = low <= self.stop_price
            target_hit = high >= self.target_price
        else:
            stop_hit = high >= self.stop_price
            target_hit = low <= self.target_price
        
        if stop_hit:
            self._close_position_with_tracking(
                self.stop_price, timestamp, bar_idx, "stop_loss", strategy_name, verbose
            )
        elif target_hit:
            self._close_position_with_tracking(
                self.target_price, timestamp, bar_idx, "take_profit", strategy_name, verbose
            )
    
    def _close_position_with_tracking(
        self,
        price: float,
        timestamp,
        bar_idx: int,
        reason: str,
        strategy_name: str,
        verbose: bool
    ):
        """Close position with ledger update and lesson generation."""
        if self.position == 0:
            return
        
        slippage = self.slippage_ticks * self.TICK_SIZE
        
        if self.position > 0:
            fill_price = price - slippage
            pnl_points = fill_price - self.entry_price
        else:
            fill_price = price + slippage
            pnl_points = self.entry_price - fill_price
        
        pnl = pnl_points * self.POINT_VALUE * abs(self.position)
        
        commission = self.commission_per_contract
        pnl -= commission
        
        self.capital += pnl
        
        direction = "LONG" if self.position > 0 else "SHORT"
        outcome = "WIN" if pnl >= 0 else "LOSS"
        
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
        
        # Generate lesson if loss
        lesson = None
        if pnl < 0:
            trade_details = TradeDetails(
                strategy=strategy_name,
                direction=direction,
                entry_price=self.entry_price,
                exit_price=fill_price,
                pnl=pnl,
                entry_time=str(self.entry_time),
                exit_time=str(timestamp),
                setup_id=getattr(self, '_current_setup_id', f"{strategy_name}_{direction}")
            )
            lesson = self.reviewer.review_and_learn(trade_details, self.learnings)
            if lesson:
                self.lessons_written += 1
        
        # Update ledger
        setup_id = getattr(self, '_current_setup_id', f"{strategy_name}_{direction}")
        self.ledger.update_outcome(
            setup_id=setup_id,
            exit_price=fill_price,
            outcome=outcome,
            pnl=pnl,
            outcome_lesson=lesson
        )
        
        if verbose:
            print(f"CLOSE {direction} @ {fill_price:.2f} P&L: ${pnl:.2f} ({reason})")
            if lesson:
                print(f"  Lesson: {lesson}")
        
        # Reset
        self.position = 0
        self.entry_price = 0.0
        self.stop_price = None
        self.target_price = None
