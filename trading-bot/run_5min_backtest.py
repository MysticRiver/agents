#!/usr/bin/env python3
"""
Backtest strategies on 5-minute REAL data from yfinance
"""
import sys
import json
from datetime import datetime
from pathlib import Path
import pandas as pd
import numpy as np
import yfinance as yf

from loguru import logger

from src.backtest.engine import BacktestEngine
from src.strategies.momentum import MACrossoverStrategy, BreakoutStrategy
from src.strategies.mean_reversion import BollingerBandStrategy
from src.strategies.volatility import KeltnerChannelStrategy, RangeExpansionStrategy
from src.strategies.fractal_model import FractalModelStrategy

logger.remove()
logger.add(sys.stdout, level="INFO", format="{time:HH:mm:ss} | {level} | {message}")


def fetch_real_data(symbol: str, interval: str, period: str):
    ticker = yf.Ticker(symbol)
    df = ticker.history(period=period, interval=interval)
    df.columns = [c.title() for c in df.columns]
    return df.dropna()


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
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
    
    return df


def run_walk_forward(engine, strategy, data, in_sample_ratio=0.7):
    split_idx = int(len(data) * in_sample_ratio)
    in_sample = data.iloc[:split_idx].copy()
    out_sample = data.iloc[split_idx:].copy()
    
    engine._reset()
    try:
        is_result = engine.run(in_sample, strategy, verbose=False)
        is_metrics = {
            "return_pct": is_result.total_return_pct,
            "sharpe": is_result.metrics.sharpe_ratio,
            "max_dd": is_result.metrics.max_drawdown_pct,
            "trades": is_result.metrics.total_trades,
            "win_rate": is_result.metrics.win_rate,
            "profit_factor": is_result.metrics.profit_factor,
        }
    except Exception as e:
        is_metrics = {"error": str(e)}
    
    engine._reset()
    try:
        oos_result = engine.run(out_sample, strategy, verbose=False)
        oos_metrics = {
            "return_pct": oos_result.total_return_pct,
            "sharpe": oos_result.metrics.sharpe_ratio,
            "max_dd": oos_result.metrics.max_drawdown_pct,
            "trades": oos_result.metrics.total_trades,
            "win_rate": oos_result.metrics.win_rate,
            "profit_factor": oos_result.metrics.profit_factor,
        }
    except Exception as e:
        oos_metrics = {"error": str(e)}
    
    return {
        "in_sample_bars": len(in_sample),
        "out_sample_bars": len(out_sample),
        "in_sample_period": f"{in_sample.index[0]} to {in_sample.index[-1]}",
        "out_sample_period": f"{out_sample.index[0]} to {out_sample.index[-1]}",
        "in_sample": is_metrics,
        "out_sample": oos_metrics
    }


def main():
    print("\n" + "=" * 80)
    print("5-MINUTE REAL DATA BACKTEST")
    print("=" * 80)
    
    symbol = "NQ=F"
    raw_data = fetch_real_data(symbol, "5m", "60d")
    
    print("\nDATA PROVENANCE:")
    print(f"  Source: yfinance (Yahoo Finance)")
    print(f"  Symbol: {symbol}")
    print(f"  Interval: 5m")
    print(f"  Rows: {len(raw_data)}")
    print(f"  Date range: {raw_data.index[0]} to {raw_data.index[-1]}")
    
    data = add_indicators(raw_data).dropna()
    print(f"  After warmup: {len(data)} bars")
    
    engine = BacktestEngine(
        initial_capital=25000.0,
        commission_per_contract=0.50,
        slippage_ticks=1.0,
        max_position_size=3,
        margin_per_contract=500.0
    )
    
    strategies = [
        ("MA_Crossover_Trend", MACrossoverStrategy(fast_period=9, slow_period=21, use_trend_filter=True)),
        ("Breakout_20_10", BreakoutStrategy(entry_period=20, exit_period=10)),
        ("BollingerBand_MR", BollingerBandStrategy()),
        ("Keltner_Channel", KeltnerChannelStrategy()),
        ("Range_Expansion", RangeExpansionStrategy()),
        ("Fractal_Relaxed", FractalModelStrategy(htf_bias_period=20, swing_strength=2, cisd_threshold=0.3)),
    ]
    
    print(f"\nTesting {len(strategies)} strategies on 5-min data...")
    print("-" * 80)
    
    results = []
    for name, strategy in strategies:
        logger.info(f"Testing {name}")
        result = run_walk_forward(engine, strategy, data)
        result["strategy"] = name
        results.append(result)
        
        oos = result["out_sample"]
        if "error" not in oos:
            print(f"{name:<20} OOS: {oos['return_pct']:>7.2f}% | "
                  f"Sharpe: {oos['sharpe']:>6.2f} | "
                  f"DD: {oos['max_dd']:>7.2f}% | "
                  f"Trades: {oos['trades']:>4} | "
                  f"WR: {oos['win_rate']:>5.1f}% | "
                  f"PF: {oos['profit_factor']:>5.2f}")
        else:
            print(f"{name:<20} ERROR: {oos['error'][:40]}")
    
    print("\n" + "=" * 80)
    print("5-MIN OUT-OF-SAMPLE SUMMARY (REAL DATA)")
    print("=" * 80)
    
    sorted_results = sorted(results, key=lambda x: x["out_sample"].get("return_pct", -999), reverse=True)
    
    for r in sorted_results:
        oos = r["out_sample"]
        if "error" not in oos:
            ret = oos["return_pct"]
            print(f"{r['strategy']:<20} {ret:>8.2f}% | Sharpe: {oos['sharpe']:>6.2f} | "
                  f"DD: {oos['max_dd']:>7.2f}% | Trades: {oos['trades']:>4}")
    
    return results


if __name__ == "__main__":
    main()
