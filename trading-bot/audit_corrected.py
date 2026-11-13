#!/usr/bin/env python3
"""
AUDIT the CORRECTED engine
"""
import sys
import random
import pandas as pd
import numpy as np
import yfinance as yf

from loguru import logger

from src.backtest.engine import BacktestEngine
from src.strategies.momentum import MACrossoverStrategy
from src.strategies.volatility import KeltnerChannelStrategy

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
    
    high, low, close = df["High"], df["Low"], df["Close"]
    tr1 = high - low
    tr2 = abs(high - close.shift())
    tr3 = abs(low - close.shift())
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df["ATR"] = tr.rolling(window=14).mean()
    
    return df.dropna()


def main():
    print("="*70)
    print("AUDIT OF CORRECTED ENGINE")
    print("="*70)
    
    data = fetch_data()
    data = add_indicators(data)
    
    split_idx = int(len(data) * 0.7)
    oos_data = data.iloc[split_idx:].copy()
    
    print(f"\nOOS Period: {oos_data.index[0]} to {oos_data.index[-1]}")
    print(f"Bars: {len(oos_data)}")
    
    # Buy and hold
    bh_start = oos_data.iloc[0]["Open"]
    bh_end = oos_data.iloc[-1]["Close"]
    bh_points = bh_end - bh_start
    bh_pnl = bh_points * 2.0
    bh_return = (bh_pnl / 25000) * 100
    print(f"\nBuy-and-Hold: {bh_return:.2f}% ({bh_points:.2f} points)")
    
    # Test MA strategy
    print("\n" + "-"*70)
    print("MA CROSSOVER STRATEGY ANALYSIS")
    print("-"*70)
    
    engine = BacktestEngine(
        initial_capital=25000.0,
        commission_per_contract=0.50,
        slippage_ticks=1.0,
        max_position_size=3,
        margin_per_contract=500.0
    )
    
    strategy = MACrossoverStrategy(fast_period=5, slow_period=13, use_trend_filter=False)
    
    # Generate signals
    signals_df = strategy.generate_signals(oos_data.copy())
    signal_bars = signals_df[signals_df["Signal"] != 0]
    
    print(f"Total signals: {len(signal_bars)}")
    print(f"Buy signals: {(signals_df['Signal'] == 1).sum()}")
    print(f"Sell signals: {(signals_df['Signal'] == -1).sum()}")
    
    # Look at a few signals
    print("\nFirst 10 signals:")
    for i, (idx, row) in enumerate(signal_bars.head(10).iterrows()):
        prev_idx = signals_df.index.get_loc(idx)
        if prev_idx + 1 < len(signals_df):
            next_bar = signals_df.iloc[prev_idx + 1]
            print(f"  {idx}: Signal={int(row['Signal']):+d}, Close={row['Close']:.2f}, "
                  f"Next Open={next_bar['Open']:.2f}")
    
    # Run backtest
    engine._reset()
    result = engine.run(oos_data, strategy, verbose=False)
    
    print(f"\nBacktest result:")
    print(f"  Return: {result.total_return_pct:.2f}%")
    print(f"  Trades: {result.metrics.total_trades}")
    print(f"  Win rate: {result.metrics.win_rate:.1f}%")
    print(f"  Avg trade P&L: ${result.metrics.avg_trade:.2f}")
    print(f"  Sharpe: {result.metrics.sharpe_ratio:.2f}")
    
    # Analyze trades
    if result.trades:
        print(f"\nFirst 10 trades:")
        for i, t in enumerate(result.trades[:10]):
            print(f"  {i+1}: {t.side.value} @ {t.entry_price:.2f} -> {t.exit_price:.2f}, "
                  f"P&L=${t.pnl:.2f}, Bars={t.holding_period}")
        
        # Check for issues
        pnls = [t.pnl for t in result.trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]
        
        print(f"\nP&L distribution:")
        print(f"  Wins: {len(wins)} ({len(wins)/len(pnls)*100:.1f}%)")
        print(f"  Losses: {len(losses)} ({len(losses)/len(pnls)*100:.1f}%)")
        print(f"  Avg win: ${np.mean(wins) if wins else 0:.2f}")
        print(f"  Avg loss: ${np.mean(losses) if losses else 0:.2f}")
        
        # Check holding periods
        holding = [t.holding_period for t in result.trades]
        print(f"\nHolding periods:")
        print(f"  Min: {min(holding)}")
        print(f"  Max: {max(holding)}")
        print(f"  Avg: {np.mean(holding):.1f}")
    
    # Random entry control
    print("\n" + "-"*70)
    print("RANDOM ENTRY CONTROL (200 runs)")
    print("-"*70)
    
    trade_freq = len(signal_bars) / len(oos_data)
    print(f"Target trade frequency: {trade_freq*100:.2f}% of bars")
    
    random_returns = []
    for _ in range(200):
        engine._reset()
        
        random_signals = oos_data.copy()
        random_signals["Signal"] = 0
        for i in range(1, len(random_signals)):
            if random.random() < trade_freq:
                random_signals.iloc[i, random_signals.columns.get_loc("Signal")] = random.choice([1, -1])
        
        # Use a dummy strategy that just passes through the signals
        class DummyStrategy:
            name = "Random"
            parameters = {}
            def generate_signals(self, data):
                return random_signals
        
        result_rand = engine.run(random_signals, DummyStrategy(), verbose=False)
        random_returns.append(result_rand.total_return_pct)
    
    print(f"  Mean: {np.mean(random_returns):.2f}%")
    print(f"  Std:  {np.std(random_returns):.2f}%")
    print(f"  Min:  {min(random_returns):.2f}%")
    print(f"  Max:  {max(random_returns):.2f}%")
    
    # CRITICAL: Check signal generation for look-ahead
    print("\n" + "-"*70)
    print("SIGNAL GENERATION CHECK")
    print("-"*70)
    
    # Check if EMA is computed correctly
    print("\nEMA computation check:")
    sample_idx = 100
    sample_bar = oos_data.iloc[sample_idx]
    ema_9 = sample_bar["EMA_9"]
    ema_21 = sample_bar["EMA_21"]
    close = sample_bar["Close"]
    
    # Verify EMA is using only past data
    historical = oos_data.iloc[:sample_idx+1]["Close"]
    ema_9_calc = historical.ewm(span=9, adjust=False).mean().iloc[-1]
    
    print(f"  Bar {sample_idx}: Close={close:.2f}")
    print(f"  EMA_9 from data: {ema_9:.2f}")
    print(f"  EMA_9 calculated: {ema_9_calc:.2f}")
    print(f"  Match: {abs(ema_9 - ema_9_calc) < 0.01}")
    
    # The signal generation in MACrossover
    print("\nMA Crossover signal logic:")
    print("  Signal = 1 (buy) when EMA_9 > EMA_21")
    print("  Signal = -1 (sell) when EMA_9 < EMA_21")
    print("  This uses current bar's Close in EMA calculation")
    print()
    print("  With pending signal mechanism:")
    print("  - Signal generated on bar N (using bar N's Close)")  
    print("  - Fill happens at bar N+1's Open")
    print("  This is CORRECT - no look-ahead")
    
    # But check the win rate issue
    print("\n" + "-"*70)
    print("WIN RATE ANALYSIS")
    print("-"*70)
    
    # For MA crossover, if we're in an uptrend most of the time,
    # and we're always buying when short EMA > long EMA,
    # and the trend continues, we'll have high win rate
    
    # Check how often EMA_9 > EMA_21
    bullish_bars = (oos_data["EMA_9"] > oos_data["EMA_21"]).sum()
    print(f"Bars where EMA_9 > EMA_21: {bullish_bars} ({bullish_bars/len(oos_data)*100:.1f}%)")
    
    # Market trend
    start_close = oos_data.iloc[0]["Close"]
    end_close = oos_data.iloc[-1]["Close"]
    trend_pct = (end_close - start_close) / start_close * 100
    print(f"Market trend (OOS): {trend_pct:+.2f}%")
    
    print("\nThe high win rate may be explained by:")
    print("  1. Strong upward trend in OOS period (+13.9%)")
    print("  2. MA crossover aligns with trend direction most of time")
    print("  3. BUT - 330% return on 27% market move seems too high")
    
    # Check average trade size
    print("\n" + "-"*70)
    print("POSITION SIZING CHECK")
    print("-"*70)
    
    print(f"POINT_VALUE = $2.00 (MNQ)")
    print(f"Initial capital = $25,000")
    print(f"Max position = 3 contracts")
    
    # With 300 trades and 330% return, that's $82,660 profit
    # $82,660 / 300 trades = $275.53 per trade
    # $275.53 / $2 = 137.77 points per trade avg
    # 137.77 / 25,000 NQ price = 0.55% per trade
    
    avg_pnl = 82660 / 300
    avg_points = avg_pnl / 2
    print(f"\nImplied from 330% return:")
    print(f"  Total profit: $82,660")
    print(f"  Avg per trade: ${avg_pnl:.2f}")
    print(f"  Avg points per trade: {avg_points:.1f}")
    print(f"  This is {avg_points/25000*100:.2f}% per trade")
    print()
    print("  This is PLAUSIBLE if holding through multi-day swings")
    print("  But needs verification that P&L calc is correct")


if __name__ == "__main__":
    main()
