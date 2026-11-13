#!/usr/bin/env python3
"""
Backtest ALL strategies on REAL market data from yfinance

DATA PROVENANCE:
- Source: yfinance (Yahoo Finance)
- Symbol: NQ=F (E-mini Nasdaq 100 futures)
- This is REAL market data, not synthetic

Walk-forward methodology:
- In-sample: First 70% for validation (DO NOT TRUST these numbers)
- Out-of-sample: Last 30% for unbiased measurement (these are the real results)
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
from src.backtest.metrics import calculate_metrics

# Import all strategies
from src.strategies.momentum import MACrossoverStrategy, BreakoutStrategy, MACDMomentumStrategy
from src.strategies.mean_reversion import RSIMeanReversionStrategy, BollingerBandStrategy, StatisticalArbitrageStrategy
from src.strategies.volatility import ATRBreakoutStrategy, RangeExpansionStrategy, KeltnerChannelStrategy
from src.strategies.time_based import OpeningRangeBreakoutStrategy, SessionMomentumStrategy
from src.strategies.fractal_model import FractalModelStrategy

logger.remove()
logger.add(sys.stdout, level="INFO", format="{time:HH:mm:ss} | {level} | {message}")


def fetch_real_data(symbol: str, interval: str, period: str):
    """Fetch real market data from yfinance"""
    logger.info(f"Fetching {symbol} {interval} data for {period}")
    ticker = yf.Ticker(symbol)
    df = ticker.history(period=period, interval=interval)
    
    if df.empty:
        raise ValueError(f"No data returned for {symbol}")
    
    # Standardize column names
    df.columns = [c.title() for c in df.columns]
    
    # Remove any rows with NaN
    df = df.dropna()
    
    return df


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add technical indicators needed by strategies"""
    df = df.copy()
    
    # Moving Averages
    df["SMA_10"] = df["Close"].rolling(10).mean()
    df["SMA_20"] = df["Close"].rolling(20).mean()
    df["SMA_50"] = df["Close"].rolling(50).mean()
    df["EMA_9"] = df["Close"].ewm(span=9, adjust=False).mean()
    df["EMA_21"] = df["Close"].ewm(span=21, adjust=False).mean()
    
    # RSI
    delta = df["Close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df["RSI"] = 100 - (100 / (1 + rs))
    
    # ATR
    high = df["High"]
    low = df["Low"]
    close = df["Close"]
    tr1 = high - low
    tr2 = abs(high - close.shift())
    tr3 = abs(low - close.shift())
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df["ATR"] = tr.rolling(window=14).mean()
    
    # Bollinger Bands
    df["BB_Mid"] = df["Close"].rolling(20).mean()
    bb_std = df["Close"].rolling(20).std()
    df["BB_Upper"] = df["BB_Mid"] + (bb_std * 2)
    df["BB_Lower"] = df["BB_Mid"] - (bb_std * 2)
    
    # Volume
    df["Volume_SMA"] = df["Volume"].rolling(20).mean()
    
    return df


def run_walk_forward(engine, strategy, data, in_sample_ratio=0.7):
    """Run walk-forward test"""
    split_idx = int(len(data) * in_sample_ratio)
    
    in_sample = data.iloc[:split_idx].copy()
    out_sample = data.iloc[split_idx:].copy()
    
    # In-sample
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
        logger.error(f"In-sample error: {e}")
        is_metrics = {"error": str(e)}
    
    # Out-of-sample
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
            "expectancy": oos_result.metrics.expectancy,
        }
    except Exception as e:
        logger.error(f"Out-of-sample error: {e}")
        oos_metrics = {"error": str(e)}
    
    return {
        "in_sample_bars": len(in_sample),
        "out_sample_bars": len(out_sample),
        "in_sample_period": f"{in_sample.index[0]} to {in_sample.index[-1]}",
        "out_sample_period": f"{out_sample.index[0]} to {out_sample.index[-1]}",
        "in_sample": is_metrics,
        "out_sample": oos_metrics
    }


def get_all_strategies():
    """Get all strategies to test"""
    return [
        # Original strategies
        ("MA_Crossover_Trend", MACrossoverStrategy(fast_period=9, slow_period=21, use_trend_filter=True)),
        ("MA_Crossover_NoTrend", MACrossoverStrategy(fast_period=5, slow_period=13, use_trend_filter=False)),
        ("Breakout_20_10", BreakoutStrategy(entry_period=20, exit_period=10)),
        ("MACD_Momentum", MACDMomentumStrategy()),
        ("RSI_MeanReversion", RSIMeanReversionStrategy()),
        ("BollingerBand_MR", BollingerBandStrategy()),
        ("StatArb_ZScore", StatisticalArbitrageStrategy()),
        ("ATR_Breakout", ATRBreakoutStrategy()),
        ("Range_Expansion", RangeExpansionStrategy()),
        ("Keltner_Channel", KeltnerChannelStrategy()),
        # Fractal Model variants
        ("Fractal_Strict", FractalModelStrategy(htf_bias_period=50, swing_strength=3, cisd_threshold=0.6)),
        ("Fractal_Medium", FractalModelStrategy(htf_bias_period=30, swing_strength=2, cisd_threshold=0.4)),
        ("Fractal_Relaxed", FractalModelStrategy(htf_bias_period=20, swing_strength=2, cisd_threshold=0.3)),
    ]


def main():
    print("\n" + "=" * 80)
    print("BACKTEST ON REAL MARKET DATA")
    print("=" * 80)
    
    # Fetch real data
    symbol = "NQ=F"
    interval = "1h"
    period = "730d"
    
    try:
        raw_data = fetch_real_data(symbol, interval, period)
    except Exception as e:
        print(f"\nFATAL: Could not fetch real data: {e}")
        print("Stopping - will not fall back to synthetic data.")
        return None
    
    # Data provenance
    print("\nDATA PROVENANCE:")
    print(f"  Source: yfinance (Yahoo Finance)")
    print(f"  Symbol: {symbol}")
    print(f"  Interval: {interval}")
    print(f"  Period requested: {period}")
    print(f"  Rows retrieved: {len(raw_data)}")
    print(f"  Date range: {raw_data.index[0]} to {raw_data.index[-1]}")
    print(f"  Price range: ${raw_data['Close'].min():.2f} to ${raw_data['Close'].max():.2f}")
    
    # Add indicators
    data = add_indicators(raw_data)
    data = data.dropna()  # Remove rows with NaN from indicator warmup
    
    print(f"  Rows after indicator warmup: {len(data)}")
    
    # Setup engine
    engine = BacktestEngine(
        initial_capital=25000.0,
        commission_per_contract=0.50,  # MNQ round trip
        slippage_ticks=1.0,
        max_position_size=3,
        margin_per_contract=500.0
    )
    
    # Test all strategies
    strategies = get_all_strategies()
    results = []
    
    print(f"\nTesting {len(strategies)} strategies...")
    print("-" * 80)
    
    for name, strategy in strategies:
        logger.info(f"Testing {name}")
        result = run_walk_forward(engine, strategy, data)
        result["strategy"] = name
        result["parameters"] = strategy.parameters
        results.append(result)
        
        oos = result["out_sample"]
        if "error" not in oos:
            print(f"{name:<25} OOS: {oos['return_pct']:>7.2f}% | "
                  f"Sharpe: {oos['sharpe']:>6.2f} | "
                  f"DD: {oos['max_dd']:>7.2f}% | "
                  f"Trades: {oos['trades']:>4} | "
                  f"WR: {oos['win_rate']:>5.1f}% | "
                  f"PF: {oos['profit_factor']:>5.2f}")
        else:
            print(f"{name:<25} ERROR: {oos['error'][:40]}")
    
    # Summary
    print("\n" + "=" * 80)
    print("OUT-OF-SAMPLE RESULTS SUMMARY (REAL DATA)")
    print("=" * 80)
    print(f"{'Strategy':<25} {'Return%':>8} {'Sharpe':>7} {'MaxDD%':>8} {'Trades':>7} {'WinRate':>8} {'PF':>6}")
    print("-" * 80)
    
    # Sort by return
    sorted_results = sorted(results, key=lambda x: x["out_sample"].get("return_pct", -999), reverse=True)
    
    profitable_count = 0
    for r in sorted_results:
        oos = r["out_sample"]
        if "error" not in oos:
            ret = oos["return_pct"]
            if ret > 0:
                profitable_count += 1
            print(f"{r['strategy']:<25} {ret:>8.2f} {oos['sharpe']:>7.2f} {oos['max_dd']:>8.2f} "
                  f"{oos['trades']:>7} {oos['win_rate']:>8.1f} {oos['profit_factor']:>6.2f}")
    
    print("-" * 80)
    print(f"Profitable strategies (OOS): {profitable_count}/{len(results)}")
    
    # Save results
    output = {
        "data_provenance": {
            "source": "yfinance (Yahoo Finance)",
            "symbol": symbol,
            "interval": interval,
            "period": period,
            "rows": len(raw_data),
            "date_range": f"{raw_data.index[0]} to {raw_data.index[-1]}",
            "price_range": f"${raw_data['Close'].min():.2f} to ${raw_data['Close'].max():.2f}",
            "is_real_data": True
        },
        "test_methodology": {
            "type": "walk_forward",
            "in_sample_ratio": 0.7,
            "initial_capital": 25000.0,
            "commission_per_contract": 0.50,
            "slippage_ticks": 1.0
        },
        "results": results
    }
    
    output_path = Path("results") / f"real_data_backtest_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    output_path.parent.mkdir(exist_ok=True)
    
    # Convert timestamps to strings for JSON
    def convert_timestamps(obj):
        if isinstance(obj, dict):
            return {k: convert_timestamps(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [convert_timestamps(v) for v in obj]
        elif isinstance(obj, (pd.Timestamp, datetime)):
            return str(obj)
        elif isinstance(obj, (np.integer, np.floating)):
            return float(obj)
        elif isinstance(obj, np.bool_):
            return bool(obj)
        return obj
    
    with open(output_path, 'w') as f:
        json.dump(convert_timestamps(output), f, indent=2)
    
    print(f"\nResults saved to: {output_path}")
    
    return output


if __name__ == "__main__":
    main()
