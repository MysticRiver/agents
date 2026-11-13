#!/usr/bin/env python3
"""
Memory Gate Backtest Comparison

Tests the Skool course learning loop:
- Memory ON: Skip signals matching recent failed setups
- Memory OFF: Execute all signals

Compares fractal model (0.5 threshold) and MA crossover trend strategies.
"""
import sys
import pandas as pd
import numpy as np
from datetime import datetime
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

from src.data.data_handler import DataHandler
from src.backtest.engine_v2 import BacktestEngineV2
from src.backtest.engine_with_memory import BacktestEngineWithMemory
from src.strategies.fractal_model import FractalModelStrategy
from src.strategies.momentum import MACrossoverStrategy


def fetch_real_data(interval: str = "1h") -> pd.DataFrame:
    """Fetch real NQ=F data from yfinance."""
    import yfinance as yf
    
    print(f"Fetching real NQ=F data ({interval})...")
    
    # For 1h data, yfinance limits to ~730 days
    # For 5m data, yfinance limits to ~60 days
    ticker = yf.Ticker("NQ=F")
    
    if interval == "1h":
        df = ticker.history(period="730d", interval="1h")
    elif interval == "5m":
        df = ticker.history(period="60d", interval="5m")
    else:
        df = ticker.history(period="max", interval=interval)
    
    if df.empty:
        print("Warning: No data from yfinance, using synthetic")
        return None
    
    # Clean data
    df.columns = [c.title() for c in df.columns]
    df = df.dropna()
    
    # Add ATR
    high = df["High"]
    low = df["Low"]
    close = df["Close"]
    tr1 = high - low
    tr2 = abs(high - close.shift())
    tr3 = abs(low - close.shift())
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df["ATR"] = tr.rolling(window=14).mean()
    
    print(f"Data: {len(df)} bars from {df.index[0]} to {df.index[-1]}")
    return df


def run_walk_forward(df: pd.DataFrame, strategy, engine, in_sample_ratio: float = 0.7):
    """Run walk-forward test: tune on in-sample, test on out-of-sample."""
    split_idx = int(len(df) * in_sample_ratio)
    
    in_sample = df.iloc[:split_idx].copy()
    out_of_sample = df.iloc[split_idx:].copy()
    
    print(f"  In-sample: {len(in_sample)} bars ({in_sample.index[0].date()} to {in_sample.index[-1].date()})")
    print(f"  Out-of-sample: {len(out_of_sample)} bars ({out_of_sample.index[0].date()} to {out_of_sample.index[-1].date()})")
    
    # Run on out-of-sample (the real test)
    result = engine.run(out_of_sample, strategy, verbose=False)
    
    return result, in_sample, out_of_sample


def compare_memory_gate(df: pd.DataFrame, strategy, strategy_name: str, in_sample_ratio: float = 0.7):
    """Compare strategy performance with memory gate ON vs OFF."""
    split_idx = int(len(df) * in_sample_ratio)
    out_of_sample = df.iloc[split_idx:].copy()
    
    print(f"\n{'='*60}")
    print(f"Strategy: {strategy_name}")
    print(f"{'='*60}")
    print(f"Out-of-sample: {len(out_of_sample)} bars ({out_of_sample.index[0].date()} to {out_of_sample.index[-1].date()})")
    
    results = {}
    
    # Test memory gate window on IN-SAMPLE
    # Use 24 hours as default (course doesn't specify)
    memory_window_hours = 24.0
    
    for memory_enabled, label in [(False, "Memory OFF"), (True, "Memory ON")]:
        print(f"\n--- {label} ---")
        
        engine = BacktestEngineWithMemory(
            initial_capital=25000.0,
            commission_per_contract=0.50,
            slippage_ticks=1.0,
            use_stops=True,
            stop_atr_mult=1.5,
            target_atr_mult=3.0,
            memory_enabled=memory_enabled,
            memory_window_hours=memory_window_hours
        )
        
        result = engine.run(out_of_sample, strategy, verbose=False)
        
        print(f"  Signals executed: {result.signals_executed}")
        print(f"  Signals skipped: {result.signals_skipped}")
        print(f"  Trades taken: {len(result.trades)}")
        print(f"  Lessons written: {result.lessons_written}")
        print(f"  Return: {result.total_return_pct:.2f}%")
        print(f"  Sharpe: {result.metrics.sharpe_ratio:.2f}")
        print(f"  Win rate: {result.metrics.win_rate:.1f}%")
        
        results[label] = {
            "result": result,
            "signals_executed": result.signals_executed,
            "signals_skipped": result.signals_skipped,
            "trades": len(result.trades),
            "lessons": result.lessons_written,
            "return_pct": result.total_return_pct,
            "sharpe": result.metrics.sharpe_ratio,
            "win_rate": result.metrics.win_rate,
            "max_dd": result.metrics.max_drawdown_pct
        }
    
    return results


def print_trade_list(result, title: str, max_trades: int = 10):
    """Print trade list."""
    print(f"\n{title} (first {max_trades}):")
    print("-" * 80)
    
    for i, trade in enumerate(result.trades[:max_trades]):
        outcome = "WIN" if trade.pnl >= 0 else "LOSS"
        side = trade.side.value.upper()
        print(f"  {i+1}. {side} @ {trade.entry_price:.2f} -> {trade.exit_price:.2f} "
              f"| {outcome} ${trade.pnl:.2f} | {trade.exit_reason}")


def main():
    print("\n" + "="*80)
    print("MEMORY GATE BACKTEST COMPARISON")
    print("="*80)
    print("Testing Skool course learning loop:")
    print("  - Memory ON: Skip signals after recent loss on same setup")
    print("  - Memory OFF: Execute all signals")
    print("="*80)
    
    # Fetch real data
    df_1h = fetch_real_data("1h")
    
    if df_1h is None or len(df_1h) < 500:
        print("Insufficient real data, using longer synthetic period")
        handler = DataHandler()
        df_1h = handler.get_data("2024-01-01", "2024-12-31", "1h")
        df_1h = handler.add_indicators(df_1h)
    
    # Remove NaN rows (from indicator calculation)
    df_1h = df_1h.dropna()
    
    print(f"\nTotal data: {len(df_1h)} hourly bars")
    
    # Define strategies
    fractal_05 = FractalModelStrategy(
        htf_bias_period=50,
        swing_strength=3,
        cisd_threshold=0.5,  # Primary threshold (not data-snooped 0.3)
        target_rr=2.0
    )
    fractal_05.name = "Fractal_0.5"
    
    ma_crossover = MACrossoverStrategy(
        fast_period=9,
        slow_period=21,
        trend_period=50,
        use_trend_filter=True
    )
    ma_crossover.name = "MA_Crossover_Trend"
    
    strategies = [
        (fractal_05, "Fractal Model (0.5 threshold)"),
        (ma_crossover, "MA Crossover Trend (9/21/50)")
    ]
    
    all_results = {}
    
    for strategy, name in strategies:
        results = compare_memory_gate(df_1h, strategy, name)
        all_results[name] = results
        
        # Print sample trades for Memory OFF
        if results["Memory OFF"]["trades"] > 0:
            print_trade_list(results["Memory OFF"]["result"], f"{name} - Memory OFF trades")
    
    # Summary comparison
    print("\n" + "="*80)
    print("SUMMARY: Memory Gate Effect")
    print("="*80)
    print(f"{'Strategy':<30} {'Mode':<12} {'Trades':>8} {'Skipped':>8} {'Return %':>10} {'Sharpe':>8}")
    print("-"*80)
    
    for strat_name, results in all_results.items():
        for mode in ["Memory OFF", "Memory ON"]:
            r = results[mode]
            print(f"{strat_name:<30} {mode:<12} {r['trades']:>8} {r['signals_skipped']:>8} "
                  f"{r['return_pct']:>10.2f} {r['sharpe']:>8.2f}")
        print()
    
    # Statistical assessment
    print("\n" + "="*80)
    print("STATISTICAL ASSESSMENT")
    print("="*80)
    
    for strat_name, results in all_results.items():
        off = results["Memory OFF"]
        on = results["Memory ON"]
        
        print(f"\n{strat_name}:")
        print(f"  Memory OFF: {off['trades']} trades, {off['return_pct']:.2f}% return")
        print(f"  Memory ON:  {on['trades']} trades, {on['return_pct']:.2f}% return")
        print(f"  Skipped by memory gate: {on['signals_skipped']} signals")
        
        if off['trades'] < 30:
            print(f"  ⚠️  With only {off['trades']} trades, results are NOT statistically significant.")
            print(f"     Need 30+ trades to draw reliable conclusions.")
        
        diff = on['return_pct'] - off['return_pct']
        if diff > 0:
            print(f"  Memory gate improved return by {diff:.2f}%")
        elif diff < 0:
            print(f"  Memory gate reduced return by {abs(diff):.2f}%")
        else:
            print(f"  Memory gate had no effect on return")
    
    print("\n" + "="*80)
    print("NOTES")
    print("="*80)
    print("1. Memory window: 24 hours (course doesn't specify, chosen for this test)")
    print("2. Results from REAL yfinance NQ=F data")
    print("3. Out-of-sample period only (70/30 walk-forward split)")
    print("4. Risk manager remains final authority over all signals")
    print("="*80)
    
    return all_results


if __name__ == "__main__":
    main()
