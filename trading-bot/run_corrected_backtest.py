#!/usr/bin/env python3
"""
CORRECTED Backtest on REAL market data

FIXES APPLIED:
1. Look-ahead bias: Signals on bar N filled at bar N+1 Open (not bar N Close)
2. Sharpe ratio: Correct periods_per_year for data frequency
3. Intrabar stops: Use High/Low, assume stop hit before target if both triggered

DATA PROVENANCE:
- Source: yfinance (Yahoo Finance)
- Symbol: NQ=F (E-mini Nasdaq 100 futures)
- This is REAL market data
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

from src.strategies.momentum import MACrossoverStrategy, BreakoutStrategy, MACDMomentumStrategy
from src.strategies.mean_reversion import RSIMeanReversionStrategy, BollingerBandStrategy, StatisticalArbitrageStrategy
from src.strategies.volatility import ATRBreakoutStrategy, RangeExpansionStrategy, KeltnerChannelStrategy
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
    
    df.columns = [c.title() for c in df.columns]
    return df.dropna()


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add technical indicators"""
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
    """Run walk-forward test with CORRECTED engine"""
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
        # Fractal Model - test 0.5 (original) and 0.3 (relaxed) on IN-SAMPLE only
        ("Fractal_Original", FractalModelStrategy(htf_bias_period=50, swing_strength=3, cisd_threshold=0.5)),
        ("Fractal_Relaxed", FractalModelStrategy(htf_bias_period=20, swing_strength=2, cisd_threshold=0.3)),
    ]


def calculate_buy_and_hold(data):
    """Calculate buy-and-hold return for comparison"""
    start_price = data.iloc[0]["Open"]
    end_price = data.iloc[-1]["Close"]
    point_change = end_price - start_price
    pnl = point_change * 2.0  # MNQ $2/point
    return_pct = (pnl / 25000) * 100
    return return_pct, point_change


def main():
    print("\n" + "=" * 80)
    print("CORRECTED BACKTEST ON REAL MARKET DATA")
    print("=" * 80)
    print("\nFixes applied:")
    print("  1. Look-ahead: Signals on bar N filled at bar N+1 Open")
    print("  2. Sharpe: Correct annualization for hourly data")
    print()
    
    # Fetch real data
    symbol = "NQ=F"
    interval = "1h"
    period = "730d"
    
    raw_data = fetch_real_data(symbol, interval, period)
    
    # Data provenance
    print("DATA PROVENANCE:")
    print(f"  Source: yfinance (Yahoo Finance)")
    print(f"  Symbol: {symbol}")
    print(f"  Interval: {interval}")
    print(f"  Rows: {len(raw_data)}")
    print(f"  Date range: {raw_data.index[0]} to {raw_data.index[-1]}")
    
    data = add_indicators(raw_data).dropna()
    print(f"  After warmup: {len(data)} bars")
    
    # Setup engine
    engine = BacktestEngine(
        initial_capital=25000.0,
        commission_per_contract=0.50,
        slippage_ticks=1.0,
        max_position_size=3,
        margin_per_contract=500.0
    )
    
    # Split data for benchmark
    split_idx = int(len(data) * 0.7)
    oos_data = data.iloc[split_idx:]
    
    # Buy and hold benchmark
    bh_return, bh_points = calculate_buy_and_hold(oos_data)
    print(f"\nBUY-AND-HOLD BENCHMARK (OOS):")
    print(f"  Period: {oos_data.index[0]} to {oos_data.index[-1]}")
    print(f"  Point change: {bh_points:.2f}")
    print(f"  Return: {bh_return:.2f}%")
    
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
            vs_bh = oos['return_pct'] - bh_return
            print(f"{name:<22} OOS: {oos['return_pct']:>7.2f}% | "
                  f"Sharpe: {oos['sharpe']:>5.2f} | "
                  f"DD: {oos['max_dd']:>7.2f}% | "
                  f"Trades: {oos['trades']:>4} | "
                  f"WR: {oos['win_rate']:>5.1f}% | "
                  f"vs B&H: {vs_bh:>+6.2f}%")
        else:
            print(f"{name:<22} ERROR: {oos['error'][:40]}")
    
    # Summary
    print("\n" + "=" * 80)
    print("CORRECTED OUT-OF-SAMPLE RESULTS (REAL DATA)")
    print("=" * 80)
    print(f"Buy-and-Hold benchmark: {bh_return:.2f}%")
    print()
    print(f"{'Strategy':<22} {'Return%':>8} {'Sharpe':>7} {'MaxDD%':>8} {'Trades':>7} {'WR':>6} {'vs B&H':>8}")
    print("-" * 80)
    
    sorted_results = sorted(results, key=lambda x: x["out_sample"].get("return_pct", -999), reverse=True)
    
    profitable = 0
    beat_bh = 0
    for r in sorted_results:
        oos = r["out_sample"]
        if "error" not in oos:
            ret = oos["return_pct"]
            vs_bh = ret - bh_return
            if ret > 0:
                profitable += 1
            if ret > bh_return:
                beat_bh += 1
            print(f"{r['strategy']:<22} {ret:>8.2f} {oos['sharpe']:>7.2f} {oos['max_dd']:>8.2f} "
                  f"{oos['trades']:>7} {oos['win_rate']:>6.1f} {vs_bh:>+8.2f}")
    
    print("-" * 80)
    print(f"Profitable: {profitable}/{len(results)}")
    print(f"Beat buy-and-hold: {beat_bh}/{len(results)}")
    
    # Save results
    output = {
        "engine_version": "corrected_v2",
        "fixes_applied": [
            "Look-ahead bias: signals on bar N filled at bar N+1 Open",
            "Sharpe ratio: correct periods_per_year for hourly data (~1638)",
            "Intrabar stops: use High/Low with conservative assumption"
        ],
        "data_provenance": {
            "source": "yfinance (Yahoo Finance)",
            "symbol": symbol,
            "interval": interval,
            "rows": len(raw_data),
            "date_range": f"{raw_data.index[0]} to {raw_data.index[-1]}",
            "is_real_data": True
        },
        "benchmark": {
            "buy_and_hold_return_pct": bh_return,
            "oos_period": f"{oos_data.index[0]} to {oos_data.index[-1]}"
        },
        "results": results
    }
    
    output_path = Path("results") / f"corrected_backtest_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    output_path.parent.mkdir(exist_ok=True)
    
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
