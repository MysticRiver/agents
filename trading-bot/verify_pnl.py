#!/usr/bin/env python3
"""
Verify P&L calculation is correct
"""
import pandas as pd
import numpy as np
import yfinance as yf

from src.backtest.engine import BacktestEngine
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
    print("="*70)
    print("P&L CALCULATION VERIFICATION")
    print("="*70)
    
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
    
    strategy = MACrossoverStrategy(fast_period=5, slow_period=13, use_trend_filter=False)
    
    result = engine.run(oos_data, strategy, verbose=False)
    
    print("\nENGINE PARAMETERS:")
    print(f"  TICK_SIZE = {engine.TICK_SIZE}")
    print(f"  TICK_VALUE = {engine.TICK_VALUE}")
    print(f"  POINT_VALUE = {engine.POINT_VALUE}")
    print(f"  Commission/contract = ${engine.commission_per_contract}")
    print(f"  Slippage ticks = {engine.slippage_ticks}")
    
    print(f"\n{'='*70}")
    print("MANUAL P&L VERIFICATION FOR FIRST 5 TRADES")
    print(f"{'='*70}")
    
    for i, t in enumerate(result.trades[:5]):
        print(f"\nTrade {i+1}:")
        print(f"  Side: {t.side.value}")
        print(f"  Entry: {t.entry_price:.2f}")
        print(f"  Exit: {t.exit_price:.2f}")
        print(f"  Reported P&L: ${t.pnl:.2f}")
        print(f"  Commission: ${t.commission:.2f}")
        
        # Manual calculation
        if t.side.value == "buy":
            # Long trade: profit = exit - entry
            points = t.exit_price - t.entry_price
        else:
            # Short trade: profit = entry - exit
            points = t.entry_price - t.exit_price
        
        gross_pnl = points * engine.POINT_VALUE * t.quantity
        net_pnl = gross_pnl - t.commission
        
        print(f"\n  Manual calculation:")
        print(f"    Points: {points:.2f}")
        print(f"    Gross P&L: {points:.2f} × ${engine.POINT_VALUE} × {t.quantity} = ${gross_pnl:.2f}")
        print(f"    Commission: ${t.commission:.2f}")
        print(f"    Net P&L: ${net_pnl:.2f}")
        print(f"    Match: {abs(net_pnl - t.pnl) < 0.01}")
    
    print(f"\n{'='*70}")
    print("AGGREGATE STATISTICS")
    print(f"{'='*70}")
    
    total_points = 0
    for t in result.trades:
        if t.side.value == "buy":
            total_points += (t.exit_price - t.entry_price)
        else:
            total_points += (t.entry_price - t.exit_price)
    
    print(f"\nTotal trades: {len(result.trades)}")
    print(f"Total points captured: {total_points:.2f}")
    print(f"Average points/trade: {total_points/len(result.trades):.2f}")
    
    market_move = oos_data.iloc[-1]["Close"] - oos_data.iloc[0]["Open"]
    print(f"\nMarket move (OOS): {market_move:.2f} points")
    print(f"Points captured / Market move: {total_points/market_move:.2f}x")
    
    total_commissions = sum(t.commission for t in result.trades)
    gross_pnl = total_points * engine.POINT_VALUE
    net_pnl = gross_pnl - total_commissions
    
    print(f"\nGross P&L: ${gross_pnl:.2f}")
    print(f"Total commissions: ${total_commissions:.2f}")
    print(f"Net P&L: ${net_pnl:.2f}")
    print(f"Net Return: {net_pnl/25000*100:.2f}%")
    print(f"Reported Return: {result.total_return_pct:.2f}%")
    
    print(f"\n{'='*70}")
    print("POINT VALUE CHECK")
    print(f"{'='*70}")
    print(f"\nCurrent POINT_VALUE = $2.00 (MNQ)")
    print(f"If this were NQ (not MNQ), POINT_VALUE = $20.00")
    
    # What would results be with NQ point value?
    nq_gross_pnl = total_points * 20.0
    nq_net_pnl = nq_gross_pnl - total_commissions
    print(f"\nWith NQ point value ($20):")
    print(f"  Gross P&L: ${nq_gross_pnl:.2f}")
    print(f"  Net P&L: ${nq_net_pnl:.2f}")
    print(f"  Net Return: {nq_net_pnl/25000*100:.2f}%")
    print(f"  This would require more capital - unrealistic")


if __name__ == "__main__":
    main()
