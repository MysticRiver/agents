#!/usr/bin/env python3
"""
Debug the engine with verbose output
"""
import pandas as pd
import numpy as np
import yfinance as yf

from src.backtest.engine import BacktestEngine, OrderSide
from src.strategies.momentum import MACrossoverStrategy


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


def main():
    data = fetch_data()
    data = add_indicators(data)
    
    split_idx = int(len(data) * 0.7)
    oos_data = data.iloc[split_idx:].copy()
    
    # Take just first 50 bars for debugging
    test_data = oos_data.iloc[:50].copy()
    
    engine = BacktestEngine(
        initial_capital=25000.0,
        commission_per_contract=0.50,
        slippage_ticks=1.0,
        max_position_size=3,
        margin_per_contract=500.0
    )
    
    strategy = MACrossoverStrategy(fast_period=5, slow_period=13, use_trend_filter=False)
    
    # Run with verbose
    result = engine.run(test_data, strategy, verbose=True)
    
    print("\n" + "="*70)
    print("TRADES FROM ENGINE")
    print("="*70)
    
    for i, t in enumerate(result.trades[:10]):
        print(f"\nTrade {i+1}:")
        print(f"  Side: {t.side.value}")
        print(f"  Entry: {t.entry_price:.2f}")
        print(f"  Exit:  {t.exit_price:.2f}")
        print(f"  P&L:   ${t.pnl:.2f}")
        print(f"  Holding: {t.holding_period} bars")


if __name__ == "__main__":
    main()
