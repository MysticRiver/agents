#!/usr/bin/env python3
"""
Investigate fractal model results - why identical returns with different trade counts?
"""
import sys
import pandas as pd
import numpy as np
import yfinance as yf

from loguru import logger
from src.backtest.engine import BacktestEngine
from src.strategies.fractal_model import FractalModelStrategy

logger.remove()
logger.add(sys.stdout, level="WARNING")


def fetch_data():
    ticker = yf.Ticker("NQ=F")
    df = ticker.history(period="730d", interval="1h")
    df.columns = [c.title() for c in df.columns]
    return df.dropna()


def add_indicators(df):
    df = df.copy()
    df["SMA_10"] = df["Close"].rolling(10).mean()
    df["SMA_20"] = df["Close"].rolling(20).mean()
    df["SMA_50"] = df["Close"].rolling(50).mean()
    df["EMA_9"] = df["Close"].ewm(span=9, adjust=False).mean()
    df["EMA_21"] = df["Close"].ewm(span=21, adjust=False).mean()
    
    delta = df["Close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df["RSI"] = 100 - (100 / (1 + rs))
    
    high, low, close = df["High"], df["Low"], df["Close"]
    tr1 = high - low
    tr2 = abs(high - close.shift())
    tr3 = abs(low - close.shift())
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df["ATR"] = tr.rolling(window=14).mean()
    
    return df.dropna()


def print_trades(result, strategy_name):
    """Print full trade list"""
    print(f"\n{'='*80}")
    print(f"FULL TRADE LIST: {strategy_name}")
    print(f"{'='*80}")
    print(f"Total trades: {len(result.trades)}")
    print(f"Total return: {result.total_return_pct:.2f}%")
    print()
    
    if not result.trades:
        print("  No trades!")
        return
    
    print(f"{'#':<3} {'Direction':<6} {'Entry Time':<25} {'Entry$':<12} {'Exit Time':<25} {'Exit$':<12} {'P&L':>10} {'Bars':>6}")
    print("-"*110)
    
    total_bars_held = 0
    for i, t in enumerate(result.trades, 1):
        direction = "LONG" if t.side.value == "buy" else "SHORT"
        print(f"{i:<3} {direction:<6} {str(t.entry_time):<25} {t.entry_price:<12.2f} "
              f"{str(t.exit_time):<25} {t.exit_price:<12.2f} {t.pnl:>10.2f} {t.holding_period:>6}")
        total_bars_held += t.holding_period
    
    print("-"*110)
    print(f"Total P&L: ${sum(t.pnl for t in result.trades):.2f}")
    print(f"Total bars held: {total_bars_held}")
    print(f"Avg holding period: {total_bars_held / len(result.trades):.1f} bars")
    
    # Time in market
    total_bars_in_data = len(result.equity_curve)
    time_in_market = total_bars_held / total_bars_in_data * 100
    print(f"Time in market: {time_in_market:.1f}%")


def main():
    data = fetch_data()
    data = add_indicators(data)
    
    split_idx = int(len(data) * 0.7)
    oos_data = data.iloc[split_idx:].copy()
    
    print(f"OOS Period: {oos_data.index[0]} to {oos_data.index[-1]}")
    print(f"OOS Bars: {len(oos_data)}")
    
    # Buy and hold
    bh_start = oos_data.iloc[0]["Open"]
    bh_end = oos_data.iloc[-1]["Close"]
    bh_points = bh_end - bh_start
    bh_pnl = bh_points * 2.0  # $2/point MNQ
    bh_return = (bh_pnl / 25000) * 100
    print(f"\nBuy-and-Hold: {bh_return:.2f}% ({bh_points:.2f} points)")
    
    engine = BacktestEngine(
        initial_capital=25000.0,
        commission_per_contract=0.50,
        slippage_ticks=1.0,
        max_position_size=3,
        margin_per_contract=500.0
    )
    
    # Test both variants
    strategies = [
        ("Fractal_Original (0.5)", FractalModelStrategy(htf_bias_period=50, swing_strength=3, cisd_threshold=0.5)),
        ("Fractal_Relaxed (0.3)", FractalModelStrategy(htf_bias_period=20, swing_strength=2, cisd_threshold=0.3)),
    ]
    
    for name, strategy in strategies:
        engine._reset()
        result = engine.run(oos_data, strategy, verbose=False)
        print_trades(result, name)
    
    # Sizing and leverage info
    print("\n" + "="*80)
    print("SIZING AND LEVERAGE INFO")
    print("="*80)
    print(f"Initial capital: $25,000")
    print(f"Contracts per trade: 1")
    print(f"MNQ point value: $2")
    print(f"Margin per contract: $500")
    print(f"Effective leverage: ${25000} capital / ${500} margin = 50:1 max")
    print(f"At 1 contract: Notional = ~$50,000 (NQ price ~25,000 * $2)")
    print(f"Leverage ratio: $50,000 / $25,000 = 2:1")
    print()
    print("For -85% RSI_MeanReversion result:")
    print("  This implies ~$21,000 loss on $25,000 capital")
    print("  At $2/point, that's ~10,500 points of losses")
    print("  Spread across 93 trades = ~113 points avg loss per trade")


if __name__ == "__main__":
    main()
