#!/usr/bin/env python3
"""
Debug fractal model by checking hit rate of each condition
"""
import pandas as pd
import numpy as np
import yfinance as yf


def fetch_data():
    """Fetch real NQ data"""
    ticker = yf.Ticker("NQ=F")
    return ticker.history(period="730d", interval="1h")


def add_swings(df: pd.DataFrame, strength: int = 3) -> pd.DataFrame:
    """Detect swing highs and lows"""
    df = df.copy()
    df['swing_high'] = False
    df['swing_low'] = False
    
    for i in range(strength, len(df) - strength):
        # Swing high: center bar has highest high in window
        window_highs = df['High'].iloc[i-strength:i+strength+1]
        if df['High'].iloc[i] == window_highs.max():
            df.iloc[i, df.columns.get_loc('swing_high')] = True
        
        # Swing low: center bar has lowest low in window
        window_lows = df['Low'].iloc[i-strength:i+strength+1]
        if df['Low'].iloc[i] == window_lows.min():
            df.iloc[i, df.columns.get_loc('swing_low')] = True
    
    return df


def add_bias(df: pd.DataFrame, period: int = 50) -> pd.DataFrame:
    """Add trend bias"""
    df = df.copy()
    df['sma_50'] = df['Close'].rolling(period).mean()
    df['bullish_bias'] = df['Close'] > df['sma_50']
    df['bearish_bias'] = df['Close'] < df['sma_50']
    return df


def detect_cisd(df: pd.DataFrame, threshold: float = 0.5) -> pd.DataFrame:
    """Detect Change in State of Delivery"""
    df = df.copy()
    df['cisd_bullish'] = False
    df['cisd_bearish'] = False
    
    for i in range(2, len(df)):
        prev_bar = df.iloc[i-1]
        curr_bar = df.iloc[i]
        
        # Bullish CISD: previous bar bearish, current bar closes strongly above previous high
        if prev_bar['Close'] < prev_bar['Open']:
            if curr_bar['Close'] > prev_bar['High']:
                range_above = curr_bar['Close'] - prev_bar['High']
                total_range = curr_bar['High'] - curr_bar['Low']
                if total_range > 0 and range_above / total_range > threshold:
                    df.iloc[i, df.columns.get_loc('cisd_bullish')] = True
        
        # Bearish CISD: previous bar bullish, current bar closes strongly below previous low
        if prev_bar['Close'] > prev_bar['Open']:
            if curr_bar['Close'] < prev_bar['Low']:
                range_below = prev_bar['Low'] - curr_bar['Close']
                total_range = curr_bar['High'] - curr_bar['Low']
                if total_range > 0 and range_below / total_range > threshold:
                    df.iloc[i, df.columns.get_loc('cisd_bearish')] = True
    
    return df


def detect_c2c3(df: pd.DataFrame) -> pd.DataFrame:
    """Detect C2/C3 candles"""
    df = df.copy()
    df['c2_bullish'] = False
    df['c3_bullish'] = False
    df['c2_bearish'] = False
    df['c3_bearish'] = False
    
    for i in range(5, len(df)):
        # Find recent swing lows
        recent_lows = df['swing_low'].iloc[i-20:i]
        recent_highs = df['swing_high'].iloc[i-20:i]
        
        if recent_lows.any():
            low_idx = recent_lows[recent_lows].index[-1]
            low_pos = df.index.get_loc(low_idx)
            bars_since_low = i - low_pos
            
            # C2 = 2 bars after swing, C3 = 3 bars after swing
            if bars_since_low == 2 and df['Close'].iloc[i] > df['Open'].iloc[i]:
                df.iloc[i, df.columns.get_loc('c2_bullish')] = True
            if bars_since_low == 3 and df['Close'].iloc[i] > df['Open'].iloc[i]:
                df.iloc[i, df.columns.get_loc('c3_bullish')] = True
        
        if recent_highs.any():
            high_idx = recent_highs[recent_highs].index[-1]
            high_pos = df.index.get_loc(high_idx)
            bars_since_high = i - high_pos
            
            if bars_since_high == 2 and df['Close'].iloc[i] < df['Open'].iloc[i]:
                df.iloc[i, df.columns.get_loc('c2_bearish')] = True
            if bars_since_high == 3 and df['Close'].iloc[i] < df['Open'].iloc[i]:
                df.iloc[i, df.columns.get_loc('c3_bearish')] = True
    
    return df


def main():
    print("Fetching real NQ=F data...")
    df = fetch_data()
    print(f"Data: {len(df)} bars from {df.index[0]} to {df.index[-1]}")
    
    # Add all indicators
    df = add_bias(df, period=50)
    df = add_swings(df, strength=3)
    df = detect_cisd(df, threshold=0.5)
    df = detect_c2c3(df)
    
    df = df.dropna()
    total = len(df)
    
    print(f"\n{'='*60}")
    print("FRACTAL MODEL CONDITION HIT RATES")
    print(f"{'='*60}")
    print(f"Total bars: {total}")
    print()
    
    # Check each condition
    conditions = [
        ("Bullish Bias (Close > SMA50)", "bullish_bias"),
        ("Bearish Bias (Close < SMA50)", "bearish_bias"),
        ("Swing High detected", "swing_high"),
        ("Swing Low detected", "swing_low"),
        ("CISD Bullish", "cisd_bullish"),
        ("CISD Bearish", "cisd_bearish"),
        ("C2 Bullish", "c2_bullish"),
        ("C3 Bullish", "c3_bullish"),
        ("C2 Bearish", "c2_bearish"),
        ("C3 Bearish", "c3_bearish"),
    ]
    
    for name, col in conditions:
        count = df[col].sum()
        pct = 100 * count / total
        print(f"{name:<35}: {count:>6} ({pct:>5.2f}%)")
    
    # Combined conditions
    print(f"\n{'='*60}")
    print("COMBINED CONDITIONS (for trade entries)")
    print(f"{'='*60}")
    
    # Bullish setup: bias + swing + cisd + c2/c3
    bullish_with_bias = df['bullish_bias'].sum()
    bullish_with_swing = (df['bullish_bias'] & df['swing_low']).sum()
    bullish_with_cisd = (df['bullish_bias'] & df['cisd_bullish']).sum()
    bullish_with_c2c3 = (df['bullish_bias'] & (df['c2_bullish'] | df['c3_bullish'])).sum()
    full_bullish = (
        df['bullish_bias'] & 
        df['cisd_bullish'] & 
        (df['c2_bullish'] | df['c3_bullish'])
    ).sum()
    
    print(f"Bullish:")
    print(f"  With bias                     : {bullish_with_bias:>6}")
    print(f"  With bias + swing low         : {bullish_with_swing:>6}")
    print(f"  With bias + CISD bullish      : {bullish_with_cisd:>6}")
    print(f"  With bias + C2/C3 bullish     : {bullish_with_c2c3:>6}")
    print(f"  Full setup (bias+cisd+c2c3)   : {full_bullish:>6}")
    
    # Bearish setup
    bearish_with_bias = df['bearish_bias'].sum()
    bearish_with_swing = (df['bearish_bias'] & df['swing_high']).sum()
    bearish_with_cisd = (df['bearish_bias'] & df['cisd_bearish']).sum()
    bearish_with_c2c3 = (df['bearish_bias'] & (df['c2_bearish'] | df['c3_bearish'])).sum()
    full_bearish = (
        df['bearish_bias'] & 
        df['cisd_bearish'] & 
        (df['c2_bearish'] | df['c3_bearish'])
    ).sum()
    
    print(f"\nBearish:")
    print(f"  With bias                     : {bearish_with_bias:>6}")
    print(f"  With bias + swing high        : {bearish_with_swing:>6}")
    print(f"  With bias + CISD bearish      : {bearish_with_cisd:>6}")
    print(f"  With bias + C2/C3 bearish     : {bearish_with_c2c3:>6}")
    print(f"  Full setup (bias+cisd+c2c3)   : {full_bearish:>6}")
    
    print(f"\n{'='*60}")
    print("BOTTLENECK ANALYSIS")
    print(f"{'='*60}")
    
    # Find the bottleneck
    cisd_rate = df['cisd_bullish'].sum() + df['cisd_bearish'].sum()
    c2c3_rate = df['c2_bullish'].sum() + df['c3_bullish'].sum() + df['c2_bearish'].sum() + df['c3_bearish'].sum()
    
    print(f"CISD signals per 1000 bars: {1000*cisd_rate/total:.1f}")
    print(f"C2/C3 signals per 1000 bars: {1000*c2c3_rate/total:.1f}")
    print(f"Full bullish setups: {full_bullish}")
    print(f"Full bearish setups: {full_bearish}")
    
    if cisd_rate < c2c3_rate:
        print("\n>>> CISD is the bottleneck - consider relaxing CISD threshold")
    else:
        print("\n>>> C2/C3 is the bottleneck - check swing detection parameters")
    
    # Recommendations
    print(f"\n{'='*60}")
    print("RELAXED PARAMETER ANALYSIS")
    print(f"{'='*60}")
    
    # Test relaxed CISD threshold
    for threshold in [0.3, 0.2, 0.1]:
        df_test = detect_cisd(df.copy(), threshold=threshold)
        cisd = df_test['cisd_bullish'].sum() + df_test['cisd_bearish'].sum()
        print(f"CISD threshold {threshold}: {cisd} signals ({1000*cisd/total:.1f}/1000 bars)")
    
    # Test relaxed swing strength
    for strength in [2, 1]:
        df_test = add_swings(df.copy(), strength=strength)
        swings = df_test['swing_high'].sum() + df_test['swing_low'].sum()
        print(f"Swing strength {strength}: {swings} swings ({1000*swings/total:.1f}/1000 bars)")


if __name__ == "__main__":
    main()
