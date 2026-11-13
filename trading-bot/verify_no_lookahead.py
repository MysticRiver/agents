#!/usr/bin/env python3
"""
Verify no look-ahead remains by shifting signals one more bar
"""
import sys
import pandas as pd
import numpy as np
import yfinance as yf

from loguru import logger
from src.backtest.engine import BacktestEngine
from src.strategies.momentum import MACrossoverStrategy

logger.remove()
logger.add(sys.stdout, level="WARNING")


def fetch_data():
    ticker = yf.Ticker("NQ=F")
    df = ticker.history(period="730d", interval="1h")
    df.columns = [c.title() for c in df.columns]
    return df.dropna()


def add_indicators(df):
    df = df.copy()
    df["EMA_9"] = df["Close"].ewm(span=9, adjust=False).mean()
    df["EMA_21"] = df["Close"].ewm(span=21, adjust=False).mean()
    df["SMA_50"] = df["Close"].rolling(50).mean()
    return df.dropna()


class DelayedStrategy:
    """Wrapper that delays signals by N bars"""
    def __init__(self, base_strategy, delay_bars=1):
        self.base = base_strategy
        self.delay = delay_bars
        self.name = f"{base_strategy.name}_delayed_{delay_bars}"
        self.parameters = base_strategy.parameters
    
    def generate_signals(self, data):
        signals_df = self.base.generate_signals(data)
        signals_df["Signal"] = signals_df["Signal"].shift(self.delay).fillna(0).astype(int)
        return signals_df


def main():
    print("="*70)
    print("LOOK-AHEAD VERIFICATION: SIGNAL DELAY TEST")
    print("="*70)
    
    data = fetch_data()
    data = add_indicators(data)
    
    split_idx = int(len(data) * 0.7)
    oos_data = data.iloc[split_idx:].copy()
    
    print(f"\nOOS Period: {oos_data.index[0]} to {oos_data.index[-1]}")
    
    engine = BacktestEngine(
        initial_capital=25000.0,
        commission_per_contract=0.50,
        slippage_ticks=1.0,
        max_position_size=3,
        margin_per_contract=500.0
    )
    
    base_strategy = MACrossoverStrategy(fast_period=5, slow_period=13, use_trend_filter=False)
    
    print(f"\nTesting MA Crossover with increasing signal delays:")
    print("-"*70)
    print(f"{'Delay':<10} {'Return%':>10} {'Sharpe':>10} {'Trades':>10} {'WinRate':>10}")
    print("-"*70)
    
    results = []
    for delay in [0, 1, 2, 3, 4, 5]:
        if delay == 0:
            strategy = base_strategy
        else:
            strategy = DelayedStrategy(base_strategy, delay)
        
        engine._reset()
        result = engine.run(oos_data, strategy, verbose=False)
        
        results.append({
            "delay": delay,
            "return": result.total_return_pct,
            "sharpe": result.metrics.sharpe_ratio,
            "trades": result.metrics.total_trades,
            "win_rate": result.metrics.win_rate
        })
        
        print(f"{delay:<10} {result.total_return_pct:>10.2f} {result.metrics.sharpe_ratio:>10.2f} "
              f"{result.metrics.total_trades:>10} {result.metrics.win_rate:>10.1f}")
    
    print("-"*70)
    
    # Analysis
    base_ret = results[0]["return"]
    delay1_ret = results[1]["return"]
    
    print(f"\nReturn drop from delay=0 to delay=1: {base_ret - delay1_ret:.2f}%")
    
    if base_ret - delay1_ret > 50:
        print("\n**WARNING**: Large drop suggests possible look-ahead issue")
    else:
        print("\n**OK**: Results stable across delays - no look-ahead bias detected")
    
    # The key insight: in a correctly implemented engine, the delay=0 result
    # already has a 1-bar delay (signal at bar N close -> fill at bar N+1 open).
    # Adding another delay should only slightly degrade performance due to
    # staleness, not collapse it.


if __name__ == "__main__":
    main()
