#!/usr/bin/env python3
"""
Detailed trace of first few trades
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
    
    strategy = MACrossoverStrategy(fast_period=5, slow_period=13, use_trend_filter=False)
    signals_df = strategy.generate_signals(oos_data)
    
    print("="*80)
    print("DETAILED TRADE TRACE")
    print("="*80)
    
    # Find signal bars
    signal_bars = signals_df[signals_df["Signal"] != 0].index.tolist()
    
    print("\nFirst 15 signal bars with prices:")
    print("-"*80)
    
    for i, idx in enumerate(signal_bars[:15]):
        bar = signals_df.loc[idx]
        bar_idx = signals_df.index.get_loc(idx)
        
        print(f"\n{i+1}. {idx}")
        print(f"   Signal: {int(bar['Signal']):+d}")
        print(f"   Open:  {bar['Open']:.2f}")
        print(f"   High:  {bar['High']:.2f}")
        print(f"   Low:   {bar['Low']:.2f}")
        print(f"   Close: {bar['Close']:.2f}")
        
        # What price would we fill at?
        if bar_idx + 1 < len(signals_df):
            next_bar = signals_df.iloc[bar_idx + 1]
            print(f"   Next bar Open: {next_bar['Open']:.2f}")
            
            # Fill price with slippage
            if bar['Signal'] == 1:
                fill = next_bar['Open'] + 0.25
                print(f"   Fill (buy): {fill:.2f} (Open + slippage)")
            else:
                fill = next_bar['Open'] - 0.25
                print(f"   Fill (sell): {fill:.2f} (Open - slippage)")
    
    # Now manually simulate trades
    print("\n" + "="*80)
    print("MANUAL TRADE SIMULATION")
    print("="*80)
    
    position = 0  # +1 long, -1 short, 0 flat
    entry_price = 0
    trade_num = 0
    
    pending_signal = 0
    
    for i in range(len(signals_df)):
        bar = signals_df.iloc[i]
        idx = signals_df.index[i]
        
        # Process pending signal
        if pending_signal != 0:
            fill_price = bar['Open']
            
            if pending_signal == 1:  # Buy
                fill_price += 0.25  # slippage
                
                if position == -1:  # Close short first
                    exit_price = fill_price  # Buy to close
                    trade_num += 1
                    pnl = (entry_price - exit_price) * 2.0 - 1.0  # points * $2 - commission
                    print(f"\nTrade {trade_num}: CLOSE SHORT")
                    print(f"  Entry: {entry_price:.2f}")
                    print(f"  Exit:  {exit_price:.2f}")
                    print(f"  P&L:   ${pnl:.2f}")
                    position = 0
                
                # Open long
                if position == 0:
                    position = 1
                    entry_price = fill_price
                    print(f"\n  OPEN LONG @ {entry_price:.2f}")
                    
            else:  # Sell
                fill_price -= 0.25  # slippage
                
                if position == 1:  # Close long first
                    exit_price = fill_price  # Sell to close
                    trade_num += 1
                    pnl = (exit_price - entry_price) * 2.0 - 1.0
                    print(f"\nTrade {trade_num}: CLOSE LONG")
                    print(f"  Entry: {entry_price:.2f}")
                    print(f"  Exit:  {exit_price:.2f}")
                    print(f"  P&L:   ${pnl:.2f}")
                    position = 0
                
                # Open short
                if position == 0:
                    position = -1
                    entry_price = fill_price
                    print(f"\n  OPEN SHORT @ {entry_price:.2f}")
            
            pending_signal = 0
            
            if trade_num >= 5:
                break
        
        # Get new signal
        signal = bar.get("Signal", 0)
        if signal != 0:
            pending_signal = signal


if __name__ == "__main__":
    main()
