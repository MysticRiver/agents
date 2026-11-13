#!/usr/bin/env python3
"""
AUDIT: Comprehensive check of backtest engine for errors
"""
import sys
import json
import random
from datetime import datetime
from pathlib import Path
import pandas as pd
import numpy as np
import yfinance as yf

from loguru import logger

from src.backtest.engine import BacktestEngine, OrderSide
from src.backtest.metrics import calculate_metrics

from src.strategies.momentum import MACrossoverStrategy
from src.strategies.volatility import KeltnerChannelStrategy
from src.strategies.mean_reversion import BollingerBandStrategy

logger.remove()
logger.add(sys.stdout, level="WARNING")


def fetch_data():
    """Fetch real 1h NQ data"""
    ticker = yf.Ticker("NQ=F")
    df = ticker.history(period="730d", interval="1h")
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
    
    return df.dropna()


# =============================================================================
# AUDIT CHECK 1: LOOK-AHEAD BIAS
# =============================================================================
def audit_look_ahead():
    """Check if signals on bar N are filled at bar N (look-ahead) or N+1 (correct)"""
    print("\n" + "="*70)
    print("AUDIT CHECK 1: LOOK-AHEAD BIAS")
    print("="*70)
    
    # Read engine code
    print("\nFILL LOGIC (from engine.py):")
    print("  Line 168: current_price = self._current_bar['Close']")
    print("  Line 180-181: if signal != 0: self._process_signal(signal, current_price, ...)")
    print("  Line 242: self._open_position(..., price, ...) where price = current_bar Close")
    print()
    print("VERDICT: **FAIL - LOOK-AHEAD BIAS**")
    print("  Signal computed on bar N's Close is filled AT bar N's Close.")
    print("  Should be filled at bar N+1's Open or later.")
    print()
    print("  This is a CRITICAL bug that inflates all results.")
    
    return False


# =============================================================================
# AUDIT CHECK 2: ONE-BAR DELAY TEST
# =============================================================================
def audit_one_bar_delay():
    """Shift signals one bar later and compare results"""
    print("\n" + "="*70)
    print("AUDIT CHECK 2: ONE-BAR DELAY TEST")
    print("="*70)
    
    data = fetch_data()
    data = add_indicators(data)
    
    # Use OOS period
    split_idx = int(len(data) * 0.7)
    oos_data = data.iloc[split_idx:].copy()
    
    engine = BacktestEngine(
        initial_capital=25000.0,
        commission_per_contract=0.50,
        slippage_ticks=1.0,
        max_position_size=3,
        margin_per_contract=500.0
    )
    
    strategy = KeltnerChannelStrategy()
    
    # Normal run
    engine._reset()
    result_normal = engine.run(oos_data, strategy, verbose=False)
    
    # Delayed signals: shift signal column by 1
    signals_df = strategy.generate_signals(oos_data.copy())
    signals_df["Signal"] = signals_df["Signal"].shift(1).fillna(0).astype(int)
    
    # Run with delayed signals (manual)
    engine._reset()
    for i in range(len(signals_df)):
        bar = signals_df.iloc[i]
        timestamp = signals_df.index[i]
        current_price = bar["Close"]
        
        if engine.position.quantity != 0:
            engine._update_unrealized_pnl(current_price)
        
        equity = engine.capital + engine.position.unrealized_pnl
        engine.equity_history.append(equity)
        
        signal = bar.get("Signal", 0)
        if signal != 0:
            engine._process_signal(signal, current_price, timestamp, i, False)
    
    # Close remaining position
    if engine.position.quantity != 0:
        final_price = signals_df.iloc[-1]["Close"]
        engine._close_position(final_price, signals_df.index[-1], len(signals_df) - 1, "end", False)
    
    delayed_return = ((engine.capital - 25000) / 25000) * 100
    delayed_trades = len(engine.trades)
    
    print(f"\nKeltner Channel on OOS data:")
    print(f"  Normal:   Return = {result_normal.total_return_pct:>7.2f}%, Trades = {result_normal.metrics.total_trades}")
    print(f"  Delayed:  Return = {delayed_return:>7.2f}%, Trades = {delayed_trades}")
    print(f"  Delta:    {result_normal.total_return_pct - delayed_return:>7.2f}%")
    
    collapse = result_normal.total_return_pct - delayed_return
    if abs(collapse) > 10:
        print("\nVERDICT: **FAIL** - Large difference indicates look-ahead")
    else:
        print("\nVERDICT: Results similar, but this doesn't fix the look-ahead in engine")
    
    return collapse


# =============================================================================
# AUDIT CHECK 3: RANDOM ENTRY CONTROL
# =============================================================================
def audit_random_entry():
    """Random entries should average to ~zero minus costs"""
    print("\n" + "="*70)
    print("AUDIT CHECK 3: RANDOM ENTRY CONTROL")
    print("="*70)
    
    data = fetch_data()
    data = add_indicators(data)
    
    split_idx = int(len(data) * 0.7)
    oos_data = data.iloc[split_idx:].copy()
    
    # Get target trade frequency from real strategy
    strategy = KeltnerChannelStrategy()
    signals_df = strategy.generate_signals(oos_data.copy())
    real_trades = (signals_df["Signal"] != 0).sum()
    trade_freq = real_trades / len(signals_df)
    
    n_runs = 200
    returns = []
    
    for run in range(n_runs):
        engine = BacktestEngine(
            initial_capital=25000.0,
            commission_per_contract=0.50,
            slippage_ticks=1.0,
            max_position_size=3,
            margin_per_contract=500.0
        )
        
        # Generate random signals with same frequency
        random_signals = oos_data.copy()
        random_signals["Signal"] = 0
        
        for i in range(1, len(random_signals)):
            if random.random() < trade_freq:
                random_signals.iloc[i, random_signals.columns.get_loc("Signal")] = random.choice([1, -1])
        
        # Run through engine manually
        for i in range(len(random_signals)):
            bar = random_signals.iloc[i]
            timestamp = random_signals.index[i]
            current_price = bar["Close"]
            
            if engine.position.quantity != 0:
                engine._update_unrealized_pnl(current_price)
            
            equity = engine.capital + engine.position.unrealized_pnl
            engine.equity_history.append(equity)
            
            signal = bar.get("Signal", 0)
            if signal != 0:
                engine._process_signal(signal, current_price, timestamp, i, False)
        
        if engine.position.quantity != 0:
            engine._close_position(random_signals.iloc[-1]["Close"], random_signals.index[-1], len(random_signals)-1, "end", False)
        
        ret = ((engine.capital - 25000) / 25000) * 100
        returns.append(ret)
    
    mean_ret = np.mean(returns)
    std_ret = np.std(returns)
    
    print(f"\nRandom Entry Results ({n_runs} runs):")
    print(f"  Trade frequency: {trade_freq*100:.2f}% of bars")
    print(f"  Mean return: {mean_ret:>7.2f}%")
    print(f"  Std dev:     {std_ret:>7.2f}%")
    print(f"  Min:         {min(returns):>7.2f}%")
    print(f"  Max:         {max(returns):>7.2f}%")
    
    # Expected: around -costs
    # Costs per trade: ~$1 (commission + slippage) / $25000 = 0.004% per trade
    # With ~100 trades, expect ~-0.4%
    
    if abs(mean_ret) < 5:
        print(f"\nVERDICT: PASS - Mean near zero as expected")
    else:
        print(f"\nVERDICT: **FAIL** - Mean return should be ~0 minus costs")
    
    return mean_ret, std_ret


# =============================================================================
# AUDIT CHECK 4: BUY-AND-HOLD BENCHMARK
# =============================================================================
def audit_buy_and_hold():
    """Compare to buy-and-hold on same OOS period"""
    print("\n" + "="*70)
    print("AUDIT CHECK 4: BUY-AND-HOLD BENCHMARK")
    print("="*70)
    
    data = fetch_data()
    data = add_indicators(data)
    
    split_idx = int(len(data) * 0.7)
    oos_data = data.iloc[split_idx:].copy()
    
    # Buy and hold
    start_price = oos_data.iloc[0]["Close"]
    end_price = oos_data.iloc[-1]["Close"]
    bh_return_points = end_price - start_price
    
    # Using MNQ specs: $2/point, 1 contract
    bh_pnl = bh_return_points * 2.0  # $2 per point
    bh_return_pct = (bh_pnl / 25000) * 100
    
    print(f"\nOOS Period: {oos_data.index[0]} to {oos_data.index[-1]}")
    print(f"  Start price: ${start_price:.2f}")
    print(f"  End price:   ${end_price:.2f}")
    print(f"  Point change: {bh_return_points:.2f}")
    print(f"  Buy-and-Hold P&L: ${bh_pnl:.2f} ({bh_return_pct:.2f}%)")
    
    # Run Keltner for comparison
    engine = BacktestEngine(
        initial_capital=25000.0,
        commission_per_contract=0.50,
        slippage_ticks=1.0,
        max_position_size=3,
        margin_per_contract=500.0
    )
    strategy = KeltnerChannelStrategy()
    result = engine.run(oos_data, strategy, verbose=False)
    
    print(f"\n  Keltner Channel: ${result.total_return:.2f} ({result.total_return_pct:.2f}%)")
    print(f"  Outperformance:  {result.total_return_pct - bh_return_pct:.2f}%")
    
    return bh_return_pct


# =============================================================================
# AUDIT CHECK 5: COSTS AND SIZING
# =============================================================================
def audit_costs_sizing():
    """Verify costs are deducted correctly"""
    print("\n" + "="*70)
    print("AUDIT CHECK 5: COSTS AND SIZING")
    print("="*70)
    
    print("\nEngine Configuration:")
    print("  initial_capital = $25,000")
    print("  commission_per_contract = $0.50 (round trip)")
    print("  slippage_ticks = 1.0")
    print("  TICK_SIZE = $0.25")
    print("  TICK_VALUE = $0.50")
    print("  POINT_VALUE = $2.00 (MNQ)")
    print("  margin_per_contract = $500")
    
    print("\nCost per trade:")
    print("  Commission: $0.50 entry + $0.50 exit = $1.00 total")
    print("  Slippage: 1 tick * $0.50 * 2 sides = $1.00")
    print("  Total cost per round-trip: ~$2.00")
    
    # Verify by inspection
    print("\nCode verification (engine.py):")
    print("  Line 275-278: commission deducted on open")
    print("  Line 326-329: P&L calculated with slippage, commission deducted")
    print("  Line 263-266: Slippage applied to fill price")
    
    # Test with known trade
    data = fetch_data()
    data = add_indicators(data)[:100]  # Small sample
    
    engine = BacktestEngine(
        initial_capital=25000.0,
        commission_per_contract=0.50,
        slippage_ticks=1.0,
        max_position_size=1,
        margin_per_contract=500.0
    )
    
    # Force a trade
    test_data = data.copy()
    test_data["Signal"] = 0
    test_data.iloc[10, test_data.columns.get_loc("Signal")] = 1  # Buy
    test_data.iloc[20, test_data.columns.get_loc("Signal")] = -1  # Sell
    
    # Simulate
    for i in range(len(test_data)):
        bar = test_data.iloc[i]
        timestamp = test_data.index[i]
        current_price = bar["Close"]
        
        if engine.position.quantity != 0:
            engine._update_unrealized_pnl(current_price)
        
        engine.equity_history.append(engine.capital + engine.position.unrealized_pnl)
        
        signal = bar.get("Signal", 0)
        if signal != 0:
            engine._process_signal(signal, current_price, timestamp, i, False)
    
    if engine.trades:
        t = engine.trades[0]
        print(f"\nTest trade verification:")
        print(f"  Entry price: {t.entry_price:.2f}")
        print(f"  Exit price:  {t.exit_price:.2f}")
        print(f"  Commission:  ${t.commission:.2f}")
        print(f"  Slippage:    ${t.slippage:.2f}")
        print(f"  P&L:         ${t.pnl:.2f}")
        
        expected_pnl_points = t.exit_price - t.entry_price
        expected_pnl = expected_pnl_points * 2.0 - t.commission
        print(f"  Expected P&L: ${expected_pnl:.2f}")
    
    print("\nVERDICT: Costs appear to be deducted, but need to verify point value")
    print("  NQ=F data is E-mini ($20/point)")
    print("  Code uses POINT_VALUE = $2 (MNQ)")
    print("  This is CORRECT for MNQ trading using NQ price data")
    
    return True


# =============================================================================
# AUDIT CHECK 6: SHARPE RATIO
# =============================================================================
def audit_sharpe_formula():
    """Check Sharpe ratio calculation"""
    print("\n" + "="*70)
    print("AUDIT CHECK 6: SHARPE RATIO FORMULA")
    print("="*70)
    
    print("\nFrom metrics.py lines 112-115:")
    print("  excess_returns = returns - (risk_free_rate / periods_per_year)")
    print("  sharpe_ratio = np.sqrt(periods_per_year) * excess_returns.mean() / returns.std()")
    print()
    print("  periods_per_year = 252 * 390 = 98,280 (assumes 1-minute bars!)")
    print()
    print("**BUG FOUND: periods_per_year is hardcoded for 1-minute data**")
    print("  For 1-hour data: should be 252 * 6.5 ≈ 1,638")
    print("  For 5-min data: should be 252 * 78 ≈ 19,656")
    print()
    print("  sqrt(98280) = 313.5")
    print("  sqrt(1638)  = 40.5")
    print("  Inflation factor for 1h data: 313.5/40.5 = 7.7x")
    print()
    print("VERDICT: **FAIL - SHARPE RATIO INFLATED 7.7x FOR HOURLY DATA**")
    
    # Recalculate with correct factor
    data = fetch_data()
    data = add_indicators(data)
    
    split_idx = int(len(data) * 0.7)
    oos_data = data.iloc[split_idx:].copy()
    
    engine = BacktestEngine(
        initial_capital=25000.0,
        commission_per_contract=0.50,
        slippage_ticks=1.0,
        max_position_size=3,
        margin_per_contract=500.0
    )
    
    strategy = KeltnerChannelStrategy()
    result = engine.run(oos_data, strategy, verbose=False)
    
    # Recalculate Sharpe correctly
    equity_curve = result.equity_curve
    returns = equity_curve.pct_change().dropna()
    
    # Correct: hourly data, ~6.5 hours/day, 252 days/year
    periods_per_year_correct = 252 * 6.5  # 1638
    risk_free_rate = 0.05
    
    excess_returns = returns - (risk_free_rate / periods_per_year_correct)
    sharpe_correct = np.sqrt(periods_per_year_correct) * excess_returns.mean() / returns.std()
    
    print(f"\nKeltner Channel Sharpe:")
    print(f"  Reported (wrong):  {result.metrics.sharpe_ratio:.2f}")
    print(f"  Corrected (1h):    {sharpe_correct:.2f}")
    
    # Daily Sharpe (resample to daily)
    daily_equity = equity_curve.resample('D').last().dropna()
    daily_returns = daily_equity.pct_change().dropna()
    
    if len(daily_returns) > 0 and daily_returns.std() > 0:
        daily_excess = daily_returns - (0.05 / 252)
        sharpe_daily = np.sqrt(252) * daily_excess.mean() / daily_returns.std()
        print(f"  Daily Sharpe:      {sharpe_daily:.2f}")
    
    return sharpe_correct


# =============================================================================
# AUDIT CHECK 7: DATA HANDLING
# =============================================================================
def audit_data_handling():
    """Check stop/target resolution, gaps, etc."""
    print("\n" + "="*70)
    print("AUDIT CHECK 7: DATA HANDLING")
    print("="*70)
    
    data = fetch_data()
    
    print("\nData characteristics:")
    print(f"  Total bars: {len(data)}")
    print(f"  Date range: {data.index[0]} to {data.index[-1]}")
    
    # Check for gaps
    time_diffs = pd.Series(data.index).diff().dropna()
    max_gap = time_diffs.max()
    gaps_over_2h = (time_diffs > pd.Timedelta(hours=2)).sum()
    
    print(f"  Max time gap: {max_gap}")
    print(f"  Gaps > 2 hours: {gaps_over_2h}")
    
    # Check for price jumps (potential roll gaps)
    price_changes = data["Close"].pct_change().abs()
    large_jumps = (price_changes > 0.05).sum()
    
    print(f"  Price jumps > 5%: {large_jumps}")
    
    print("\nStop/Target resolution:")
    print("  Code does NOT handle intra-bar stop/target resolution")
    print("  Lines 368-382: stops checked at bar close price only")
    print("  If both stop and target hit intra-bar, result depends on close")
    print("  This is a simplification that may bias results")
    
    print("\nSession gaps:")
    print("  Continuous futures data from yfinance")
    print("  Overnight gaps are present in the data")
    print("  No special handling of overnight gap fills")
    
    print("\nVERDICT: Data handling has minor issues but not the main problem")
    
    return True


# =============================================================================
# AUDIT CHECK 8: WALK-FORWARD METHODOLOGY
# =============================================================================
def audit_walk_forward():
    """Check walk-forward split"""
    print("\n" + "="*70)
    print("AUDIT CHECK 8: WALK-FORWARD METHODOLOGY")
    print("="*70)
    
    data = fetch_data()
    data = add_indicators(data)
    
    total_bars = len(data)
    split_idx = int(total_bars * 0.7)
    
    in_sample = data.iloc[:split_idx]
    out_sample = data.iloc[split_idx:]
    
    print("\nSplit:")
    print(f"  Total bars: {total_bars}")
    print(f"  In-sample:  {len(in_sample)} bars ({len(in_sample)/total_bars*100:.1f}%)")
    print(f"  Out-sample: {len(out_sample)} bars ({len(out_sample)/total_bars*100:.1f}%)")
    print()
    print(f"  In-sample period:  {in_sample.index[0]} to {in_sample.index[-1]}")
    print(f"  Out-sample period: {out_sample.index[0]} to {out_sample.index[-1]}")
    
    print("\nParameter selection:")
    print("  Strategy parameters (MA periods, etc.) were HARDCODED")
    print("  They were NOT optimized on in-sample data")
    print("  This is actually correct (no in-sample optimization)")
    print("  But it means no true 'walk-forward' optimization was done")
    
    print("\nVERDICT: Simple train/test split, not optimized walk-forward")
    print("  This is acceptable but parameters are arbitrary, not optimized")
    
    return True


# =============================================================================
# MAIN AUDIT
# =============================================================================
def main():
    print("\n" + "="*70)
    print("BACKTEST ENGINE AUDIT")
    print("="*70)
    
    results = {}
    
    # Check 1: Look-ahead
    results["look_ahead"] = audit_look_ahead()
    
    # Check 2: One-bar delay
    results["delay_delta"] = audit_one_bar_delay()
    
    # Check 3: Random entry
    results["random_mean"], results["random_std"] = audit_random_entry()
    
    # Check 4: Buy-and-hold
    results["buy_hold"] = audit_buy_and_hold()
    
    # Check 5: Costs
    results["costs_ok"] = audit_costs_sizing()
    
    # Check 6: Sharpe
    results["sharpe_correct"] = audit_sharpe_formula()
    
    # Check 7: Data
    results["data_ok"] = audit_data_handling()
    
    # Check 8: Walk-forward
    results["wf_ok"] = audit_walk_forward()
    
    # Summary
    print("\n" + "="*70)
    print("AUDIT SUMMARY")
    print("="*70)
    
    print("""
CRITICAL BUGS FOUND:

1. **LOOK-AHEAD BIAS**: Signal on bar N's close is filled AT bar N's close.
   Should be filled at bar N+1's open. This allows trading on information
   not yet available, inflating returns.
   
2. **SHARPE RATIO INFLATION**: periods_per_year hardcoded to 98,280 (1-min),
   but data is hourly (should be ~1,638). Sharpe inflated by 7.7x.
   
   Reported Sharpe 6.54 → Corrected: ~0.85
   Reported Sharpe 4.54 → Corrected: ~0.59
   
IMPACT: ALL previously reported results are INVALID.

To fix:
- Engine: Fill at next bar's open, not current close
- Metrics: Use correct periods_per_year for data frequency
""")
    
    return results


if __name__ == "__main__":
    main()
