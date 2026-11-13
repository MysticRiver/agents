#!/usr/bin/env python3
"""
Final backtest with corrected engine V2 - stops anchored to entry price
"""
import sys
import json
from datetime import datetime
from pathlib import Path
import pandas as pd
import numpy as np
import yfinance as yf

from loguru import logger

from src.backtest.engine_v2 import BacktestEngineV2

from src.strategies.momentum import MACrossoverStrategy, BreakoutStrategy, MACDMomentumStrategy
from src.strategies.mean_reversion import RSIMeanReversionStrategy, BollingerBandStrategy, StatisticalArbitrageStrategy
from src.strategies.volatility import ATRBreakoutStrategy, RangeExpansionStrategy, KeltnerChannelStrategy
from src.strategies.fractal_model import FractalModelStrategy

logger.remove()
logger.add(sys.stdout, level="INFO", format="{time:HH:mm:ss} | {level} | {message}")


def fetch_data(interval="1h", period="730d"):
    ticker = yf.Ticker("NQ=F")
    df = ticker.history(period=period, interval=interval)
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
    
    df["BB_Mid"] = df["Close"].rolling(20).mean()
    bb_std = df["Close"].rolling(20).std()
    df["BB_Upper"] = df["BB_Mid"] + (bb_std * 2)
    df["BB_Lower"] = df["BB_Mid"] - (bb_std * 2)
    df["Volume_SMA"] = df["Volume"].rolling(20).mean()
    
    return df.dropna()


def print_trades(result, strategy_name, max_trades=20):
    """Print trade list"""
    print(f"\n{'='*100}")
    print(f"{strategy_name}: {len(result.trades)} trades, Return: {result.total_return_pct:.2f}%")
    print(f"{'='*100}")
    
    if not result.trades:
        print("  No trades!")
        return
    
    print(f"{'#':<3} {'Dir':<5} {'Entry Time':<20} {'Entry$':<10} {'Exit Time':<20} "
          f"{'Exit$':<10} {'P&L':>8} {'Bars':>5} {'Reason':<12}")
    print("-"*100)
    
    total_bars = 0
    for i, t in enumerate(result.trades[:max_trades], 1):
        direction = "LONG" if t.side.value == "buy" else "SHORT"
        entry_str = str(t.entry_time)[:19]
        exit_str = str(t.exit_time)[:19]
        print(f"{i:<3} {direction:<5} {entry_str:<20} {t.entry_price:<10.2f} {exit_str:<20} "
              f"{t.exit_price:<10.2f} {t.pnl:>8.2f} {t.holding_period:>5} {t.exit_reason:<12}")
        total_bars += t.holding_period
    
    if len(result.trades) > max_trades:
        print(f"... and {len(result.trades) - max_trades} more trades")
    
    print("-"*100)
    print(f"Total P&L: ${sum(t.pnl for t in result.trades):.2f}")
    print(f"Avg holding: {total_bars/len(result.trades):.1f} bars")
    print(f"Time in market: {total_bars/len(result.equity_curve)*100:.1f}%")
    
    # Win/loss breakdown by exit reason
    reasons = {}
    for t in result.trades:
        r = t.exit_reason
        if r not in reasons:
            reasons[r] = {"count": 0, "pnl": 0}
        reasons[r]["count"] += 1
        reasons[r]["pnl"] += t.pnl
    
    print("\nBy exit reason:")
    for r, stats in reasons.items():
        print(f"  {r}: {stats['count']} trades, ${stats['pnl']:.2f}")


def run_strategies_1h():
    """Run all strategies on 1-hour data"""
    print("\n" + "="*100)
    print("1-HOUR DATA BACKTEST (with corrected stops)")
    print("="*100)
    
    data = fetch_data("1h", "730d")
    data = add_indicators(data)
    
    split_idx = int(len(data) * 0.7)
    oos_data = data.iloc[split_idx:].copy()
    
    print(f"\nOOS: {oos_data.index[0]} to {oos_data.index[-1]} ({len(oos_data)} bars)")
    
    # Buy and hold
    bh_points = oos_data.iloc[-1]["Close"] - oos_data.iloc[0]["Open"]
    bh_return = (bh_points * 2.0 / 25000) * 100
    print(f"Buy-and-Hold: {bh_return:.2f}% ({bh_points:.2f} points)")
    
    engine = BacktestEngineV2(
        initial_capital=25000.0,
        commission_per_contract=0.50,
        slippage_ticks=1.0,
        use_stops=True,
        stop_atr_mult=1.5,
        target_atr_mult=3.0
    )
    
    strategies = [
        ("Fractal_0.5 (TTrades)", FractalModelStrategy(htf_bias_period=50, swing_strength=3, cisd_threshold=0.5)),
        ("Fractal_0.3 (snooped)", FractalModelStrategy(htf_bias_period=20, swing_strength=2, cisd_threshold=0.3)),
        ("MA_Crossover_Trend", MACrossoverStrategy(fast_period=9, slow_period=21, use_trend_filter=True)),
        ("Breakout_20_10", BreakoutStrategy(entry_period=20, exit_period=10)),
        ("Keltner_Channel", KeltnerChannelStrategy()),
        ("RSI_MeanReversion", RSIMeanReversionStrategy()),
        ("BollingerBand_MR", BollingerBandStrategy()),
    ]
    
    results = []
    
    for name, strategy in strategies:
        engine._reset()
        result = engine.run(oos_data, strategy, verbose=False)
        
        results.append({
            "name": name,
            "return": result.total_return_pct,
            "sharpe": result.metrics.sharpe_ratio,
            "max_dd": result.metrics.max_drawdown_pct,
            "trades": result.metrics.total_trades,
            "win_rate": result.metrics.win_rate,
            "result": result
        })
        
        print_trades(result, name)
    
    # Summary
    print("\n" + "="*100)
    print("1-HOUR SUMMARY (stops enabled, anchored to entry)")
    print("="*100)
    print(f"Buy-and-Hold benchmark: {bh_return:.2f}%")
    print()
    print(f"{'Strategy':<25} {'Return':>8} {'Sharpe':>7} {'MaxDD':>8} {'Trades':>7} {'WinRate':>8} {'vs B&H':>8}")
    print("-"*80)
    
    for r in sorted(results, key=lambda x: x["return"], reverse=True):
        vs_bh = r["return"] - bh_return
        print(f"{r['name']:<25} {r['return']:>8.2f} {r['sharpe']:>7.2f} {r['max_dd']:>8.2f} "
              f"{r['trades']:>7} {r['win_rate']:>8.1f} {vs_bh:>+8.2f}")
    
    return results


def run_fractal_5m():
    """Run fractal model on 5-minute data"""
    print("\n" + "="*100)
    print("5-MINUTE DATA BACKTEST (Fractal Model only)")
    print("="*100)
    
    data = fetch_data("5m", "60d")
    data = add_indicators(data)
    
    split_idx = int(len(data) * 0.7)
    oos_data = data.iloc[split_idx:].copy()
    
    print(f"\nOOS: {oos_data.index[0]} to {oos_data.index[-1]} ({len(oos_data)} bars)")
    print(f"WARNING: Short OOS period (~3 weeks)")
    
    bh_points = oos_data.iloc[-1]["Close"] - oos_data.iloc[0]["Open"]
    bh_return = (bh_points * 2.0 / 25000) * 100
    print(f"Buy-and-Hold: {bh_return:.2f}%")
    
    engine = BacktestEngineV2(
        initial_capital=25000.0,
        commission_per_contract=0.50,
        slippage_ticks=1.0,
        use_stops=True,
        stop_atr_mult=1.5,
        target_atr_mult=3.0
    )
    
    strategies = [
        ("Fractal_0.5 (TTrades)", FractalModelStrategy(htf_bias_period=50, swing_strength=3, cisd_threshold=0.5)),
        ("Fractal_0.3 (snooped)", FractalModelStrategy(htf_bias_period=20, swing_strength=2, cisd_threshold=0.3)),
    ]
    
    for name, strategy in strategies:
        engine._reset()
        result = engine.run(oos_data, strategy, verbose=False)
        print_trades(result, name)
        
        print(f"\n{name}: Return={result.total_return_pct:.2f}%, "
              f"Sharpe={result.metrics.sharpe_ratio:.2f}, Trades={len(result.trades)}")


def main():
    print("="*100)
    print("FINAL CORRECTED BACKTEST")
    print("="*100)
    print("\nFixes applied:")
    print("  1. Signals on bar N filled at bar N+1 Open")
    print("  2. Stops/targets anchored to ENTRY price (bar N+1 Open + slippage)")
    print("  3. Conservative: stop assumed hit first if both could trigger")
    print("  4. Sharpe annualized correctly for data frequency")
    
    run_strategies_1h()
    run_fractal_5m()
    
    print("\n" + "="*100)
    print("SIZING NOTE")
    print("="*100)
    print("Initial capital: $25,000")
    print("Contracts: 1 per trade")
    print("MNQ point value: $2")
    print("Margin: $500/contract")
    print("Leverage: ~2:1 (notional ~$50k on $25k capital)")


if __name__ == "__main__":
    main()
