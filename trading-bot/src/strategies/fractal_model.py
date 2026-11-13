"""
TTrades Fractal Model Strategy Implementation

Rules derived from TTrades.com sources (see docs/fractal-ai-bot-report.md for attribution):
- https://ttrades.com/the-only-trading-strategy-you-need-for-2026/
- https://ttrades.com/the-best-timeframes-for-ttrades-fractal-model-simple/
- https://ttrades.com/how-change-in-the-state-of-delivery-cisd-confirms-swing-points/
- TTrades Alignment with Bias PDF

Key Concepts:
1. Price cannot reverse without forming a swing point
2. Candle numbering: C1 (before swing), C2 (swing/reversal), C3 (expansion)
3. CISD = Change in State of Delivery (LTF confirmation)
4. Multi-timeframe alignment required (HTF bias → MTF structure → LTF entry)
"""
import pandas as pd
import numpy as np
from typing import Optional, Tuple, Dict, List
from .base import BaseStrategy
from loguru import logger


class FractalModelStrategy(BaseStrategy):
    """
    TTrades Fractal Model Strategy
    
    Core rules (SOURCE: TTrades website articles):
    1. Establish daily bias from prior day close vs PDH/PDL
    2. Identify swing points (C2 candles) at points of interest
    3. Confirm with CISD on lower timeframe
    4. Enter on continuation (C3) with stop beyond protected swing
    5. Target 2R or higher timeframe objective
    
    INTERPRETATION NOTES (not from source):
    - Using EMA trend filter as proxy for daily bias in single-TF backtest
    - FVG detection simplified to consecutive candle gaps
    - CISD approximated by momentum shift detection
    """
    
    def __init__(
        self,
        # Timeframe alignment (MY INTERPRETATION: using lookback periods as proxy)
        htf_bias_period: int = 50,  # Higher TF bias (trend)
        swing_lookback: int = 10,   # Candles to identify swing
        
        # Swing point detection
        swing_strength: int = 3,    # Bars left/right for swing confirmation
        
        # FVG parameters (SOURCE: TTrades mentions FVGs as points of interest)
        fvg_min_size_atr: float = 0.5,  # MY INTERPRETATION: min FVG size as ATR multiple
        
        # CISD parameters (MY INTERPRETATION of "change in state of delivery")
        cisd_lookback: int = 5,
        cisd_threshold: float = 0.6,  # Momentum shift threshold
        
        # Risk management (SOURCE: TTrades mentions 2R targets)
        atr_period: int = 14,
        stop_atr_multiplier: float = 1.5,
        target_rr: float = 2.0,
        
        # Entry timing
        require_continuation: bool = True,
    ):
        super().__init__(
            name="TTrades_Fractal_Model",
            htf_bias_period=htf_bias_period,
            swing_lookback=swing_lookback,
            swing_strength=swing_strength,
            fvg_min_size_atr=fvg_min_size_atr,
            cisd_lookback=cisd_lookback,
            cisd_threshold=cisd_threshold,
            atr_period=atr_period,
            stop_atr_multiplier=stop_atr_multiplier,
            target_rr=target_rr,
            require_continuation=require_continuation
        )
        self.htf_bias_period = htf_bias_period
        self.swing_lookback = swing_lookback
        self.swing_strength = swing_strength
        self.fvg_min_size_atr = fvg_min_size_atr
        self.cisd_lookback = cisd_lookback
        self.cisd_threshold = cisd_threshold
        self.atr_period = atr_period
        self.stop_atr_multiplier = stop_atr_multiplier
        self.target_rr = target_rr
        self.require_continuation = require_continuation
        
    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """Generate signals based on TTrades Fractal Model"""
        if not self._validate_data(data):
            raise ValueError("Invalid data")
            
        df = data.copy()
        
        # Step 1: Calculate HTF bias (SOURCE: "daily bias comes first")
        df = self._calculate_bias(df)
        
        # Step 2: Identify swing points (SOURCE: "price cannot reverse without swing")
        df = self._identify_swing_points(df)
        
        # Step 3: Detect Fair Value Gaps (SOURCE: "points of interest")
        df = self._detect_fvgs(df)
        
        # Step 4: Detect CISD (SOURCE: "change in state of delivery")
        df = self._detect_cisd(df)
        
        # Step 5: Identify C2 closures (SOURCE: "candle 2 closure")
        df = self._identify_c2_closures(df)
        
        # Step 6: Generate entry signals on C3 (SOURCE: "trade candle 3")
        df = self._generate_entry_signals(df)
        
        # Step 7: Calculate stops and targets
        df = self._calculate_stops_targets(df)
        
        return df
    
    def _calculate_bias(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate higher timeframe bias
        
        SOURCE: TTrades - "daily candle close relative to previous day's range"
        - Close above PDH = bullish continuation
        - Close below PDL = bearish continuation
        - Sweep PDL + close above = bullish reversal
        - Sweep PDH + close below = bearish reversal
        
        MY INTERPRETATION: In single-timeframe backtest, using EMA as proxy
        """
        df["ATR"] = self.calculate_atr(df, self.atr_period)
        
        # Trend bias using EMA (proxy for HTF bias in single-TF)
        df["EMA_Bias"] = self.calculate_ema(df["Close"], self.htf_bias_period)
        df["Bias"] = 0
        df.loc[df["Close"] > df["EMA_Bias"], "Bias"] = 1   # Bullish
        df.loc[df["Close"] < df["EMA_Bias"], "Bias"] = -1  # Bearish
        
        # Previous high/low (approximating daily structure)
        df["PDH"] = df["High"].rolling(window=self.swing_lookback).max().shift(1)
        df["PDL"] = df["Low"].rolling(window=self.swing_lookback).min().shift(1)
        
        # Detect sweeps (SOURCE: "sweep PDH/PDL and close back")
        df["Sweep_High"] = (df["High"] > df["PDH"]) & (df["Close"] < df["PDH"])
        df["Sweep_Low"] = (df["Low"] < df["PDL"]) & (df["Close"] > df["PDL"])
        
        # Reversal bias from sweeps
        df.loc[df["Sweep_Low"], "Bias"] = 1   # Bullish reversal
        df.loc[df["Sweep_High"], "Bias"] = -1  # Bearish reversal
        
        return df
    
    def _identify_swing_points(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Identify swing highs and lows
        
        SOURCE: TTrades - "price cannot reverse without forming a swing point"
        """
        n = self.swing_strength
        
        df["Swing_High"] = False
        df["Swing_Low"] = False
        df["Protected_High"] = np.nan
        df["Protected_Low"] = np.nan
        
        for i in range(n, len(df) - n):
            # Swing high: highest of n bars on each side
            if df["High"].iloc[i] == df["High"].iloc[i-n:i+n+1].max():
                if df["High"].iloc[i] > df["High"].iloc[i-1] and df["High"].iloc[i] > df["High"].iloc[i+1]:
                    df.iloc[i, df.columns.get_loc("Swing_High")] = True
                    
            # Swing low: lowest of n bars on each side
            if df["Low"].iloc[i] == df["Low"].iloc[i-n:i+n+1].min():
                if df["Low"].iloc[i] < df["Low"].iloc[i-1] and df["Low"].iloc[i] < df["Low"].iloc[i+1]:
                    df.iloc[i, df.columns.get_loc("Swing_Low")] = True
        
        # Track most recent protected swings (SOURCE: "protected swing defines risk")
        last_swing_high = np.nan
        last_swing_low = np.nan
        
        for i in range(len(df)):
            if df["Swing_High"].iloc[i]:
                last_swing_high = df["High"].iloc[i]
            if df["Swing_Low"].iloc[i]:
                last_swing_low = df["Low"].iloc[i]
            df.iloc[i, df.columns.get_loc("Protected_High")] = last_swing_high
            df.iloc[i, df.columns.get_loc("Protected_Low")] = last_swing_low
            
        return df
    
    def _detect_fvgs(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Detect Fair Value Gaps (imbalances)
        
        SOURCE: TTrades - "points of interest are fair value gaps and previous highs/lows"
        
        FVG = gap between candle bodies where price moves too fast
        """
        df["FVG_Bullish"] = False
        df["FVG_Bearish"] = False
        df["FVG_High"] = np.nan
        df["FVG_Low"] = np.nan
        
        min_gap = df["ATR"] * self.fvg_min_size_atr
        
        for i in range(2, len(df)):
            # Bullish FVG: gap up (candle 3 low > candle 1 high)
            if df["Low"].iloc[i] > df["High"].iloc[i-2]:
                gap_size = df["Low"].iloc[i] - df["High"].iloc[i-2]
                if gap_size > min_gap.iloc[i]:
                    df.iloc[i, df.columns.get_loc("FVG_Bullish")] = True
                    df.iloc[i, df.columns.get_loc("FVG_High")] = df["Low"].iloc[i]
                    df.iloc[i, df.columns.get_loc("FVG_Low")] = df["High"].iloc[i-2]
                    
            # Bearish FVG: gap down (candle 3 high < candle 1 low)
            if df["High"].iloc[i] < df["Low"].iloc[i-2]:
                gap_size = df["Low"].iloc[i-2] - df["High"].iloc[i]
                if gap_size > min_gap.iloc[i]:
                    df.iloc[i, df.columns.get_loc("FVG_Bearish")] = True
                    df.iloc[i, df.columns.get_loc("FVG_High")] = df["Low"].iloc[i-2]
                    df.iloc[i, df.columns.get_loc("FVG_Low")] = df["High"].iloc[i]
        
        return df
    
    def _detect_cisd(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Detect Change in State of Delivery (CISD)
        
        SOURCE: TTrades - "CISD on its own means nothing unless paired with HTF candle closure"
        "When I get a C2 or C3 closure on HTF, drop down to LTF, must see CISD"
        
        MY INTERPRETATION: Detecting momentum shift as proxy for delivery change
        """
        # Calculate momentum indicator
        df["Momentum"] = df["Close"].diff(self.cisd_lookback)
        df["Momentum_Norm"] = df["Momentum"] / df["ATR"]
        
        # CISD bullish: momentum shifts from negative to positive
        df["CISD_Bullish"] = (
            (df["Momentum_Norm"] > self.cisd_threshold) &
            (df["Momentum_Norm"].shift(1) < 0)
        )
        
        # CISD bearish: momentum shifts from positive to negative
        df["CISD_Bearish"] = (
            (df["Momentum_Norm"] < -self.cisd_threshold) &
            (df["Momentum_Norm"].shift(1) > 0)
        )
        
        return df
    
    def _identify_c2_closures(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Identify Candle 2 closures (swing/reversal candles)
        
        SOURCE: TTrades - "Candle 2 will always be the swing low or swing high"
        "Looking for a candle 2 closure that aligns with daily bias"
        """
        df["C2_Bullish"] = False
        df["C2_Bearish"] = False
        
        for i in range(1, len(df)):
            # Bullish C2: Sweep low and close above (reversal)
            # Or: Strong close after testing swing low
            if df["Swing_Low"].iloc[i] or (
                df["Low"].iloc[i] <= df["Protected_Low"].iloc[i] * 1.001 and
                df["Close"].iloc[i] > df["Open"].iloc[i]
            ):
                if df["Bias"].iloc[i] >= 0:  # Aligned with bullish bias
                    df.iloc[i, df.columns.get_loc("C2_Bullish")] = True
                    
            # Bearish C2: Sweep high and close below (reversal)
            if df["Swing_High"].iloc[i] or (
                df["High"].iloc[i] >= df["Protected_High"].iloc[i] * 0.999 and
                df["Close"].iloc[i] < df["Open"].iloc[i]
            ):
                if df["Bias"].iloc[i] <= 0:  # Aligned with bearish bias
                    df.iloc[i, df.columns.get_loc("C2_Bearish")] = True
        
        return df
    
    def _generate_entry_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Generate entry signals on C3 (continuation candle)
        
        SOURCE: TTrades - "trade candle 3", "enter on continuation after CISD"
        "entries are taken on the next continuation candle"
        """
        df["Signal"] = 0
        
        for i in range(2, len(df)):
            # Bullish entry: C2 bullish + CISD confirmed + continuation
            if df["C2_Bullish"].iloc[i-1] and df["CISD_Bullish"].iloc[i-1]:
                # C3 continuation: close above prior close
                if df["Close"].iloc[i] > df["Close"].iloc[i-1]:
                    if df["Bias"].iloc[i] >= 0:  # Still aligned
                        df.iloc[i, df.columns.get_loc("Signal")] = 1
                        
            # Bearish entry: C2 bearish + CISD confirmed + continuation
            if df["C2_Bearish"].iloc[i-1] and df["CISD_Bearish"].iloc[i-1]:
                # C3 continuation: close below prior close
                if df["Close"].iloc[i] < df["Close"].iloc[i-1]:
                    if df["Bias"].iloc[i] <= 0:  # Still aligned
                        df.iloc[i, df.columns.get_loc("Signal")] = -1
        
        return df
    
    def _calculate_stops_targets(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate stop loss and take profit levels
        
        SOURCE: TTrades - "stops are placed beyond the protected swing"
        "initial target is 2R"
        """
        df["StopLoss"] = np.nan
        df["TakeProfit"] = np.nan
        
        for i in range(len(df)):
            if df["Signal"].iloc[i] == 1:  # Long
                # Stop below protected swing (SOURCE: "beyond protected swing")
                stop = df["Protected_Low"].iloc[i]
                if pd.isna(stop):
                    stop = df["Close"].iloc[i] - (df["ATR"].iloc[i] * self.stop_atr_multiplier)
                else:
                    stop = stop - (df["ATR"].iloc[i] * 0.25)  # Buffer
                    
                risk = df["Close"].iloc[i] - stop
                target = df["Close"].iloc[i] + (risk * self.target_rr)  # 2R target
                
                df.iloc[i, df.columns.get_loc("StopLoss")] = stop
                df.iloc[i, df.columns.get_loc("TakeProfit")] = target
                
            elif df["Signal"].iloc[i] == -1:  # Short
                # Stop above protected swing
                stop = df["Protected_High"].iloc[i]
                if pd.isna(stop):
                    stop = df["Close"].iloc[i] + (df["ATR"].iloc[i] * self.stop_atr_multiplier)
                else:
                    stop = stop + (df["ATR"].iloc[i] * 0.25)  # Buffer
                    
                risk = stop - df["Close"].iloc[i]
                target = df["Close"].iloc[i] - (risk * self.target_rr)  # 2R target
                
                df.iloc[i, df.columns.get_loc("StopLoss")] = stop
                df.iloc[i, df.columns.get_loc("TakeProfit")] = target
        
        # Forward fill for position management
        df["StopLoss"] = df["StopLoss"].ffill()
        df["TakeProfit"] = df["TakeProfit"].ffill()
        
        return df


class FractalModelWithFVGStrategy(FractalModelStrategy):
    """
    Enhanced Fractal Model with FVG retest requirement
    
    SOURCE: TTrades - "price needs to react from a clear point of interest"
    
    MY INTERPRETATION: Requiring price to retrace to FVG before entry
    """
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = "TTrades_Fractal_FVG"
        
    def _generate_entry_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """Entry only when price retests an FVG"""
        df["Signal"] = 0
        
        # Track active FVGs
        active_bullish_fvg = None
        active_bearish_fvg = None
        
        for i in range(2, len(df)):
            # Update active FVGs
            if df["FVG_Bullish"].iloc[i]:
                active_bullish_fvg = (df["FVG_Low"].iloc[i], df["FVG_High"].iloc[i])
            if df["FVG_Bearish"].iloc[i]:
                active_bearish_fvg = (df["FVG_Low"].iloc[i], df["FVG_High"].iloc[i])
                
            # Bullish: C2 + CISD + price retests bullish FVG
            if df["C2_Bullish"].iloc[i-1] and df["CISD_Bullish"].iloc[i-1]:
                if active_bullish_fvg is not None:
                    fvg_low, fvg_high = active_bullish_fvg
                    # Price dipped into FVG zone
                    if df["Low"].iloc[i] <= fvg_high and df["Close"].iloc[i] > fvg_low:
                        if df["Bias"].iloc[i] >= 0:
                            df.iloc[i, df.columns.get_loc("Signal")] = 1
                            active_bullish_fvg = None  # FVG filled
                            
            # Bearish: C2 + CISD + price retests bearish FVG
            if df["C2_Bearish"].iloc[i-1] and df["CISD_Bearish"].iloc[i-1]:
                if active_bearish_fvg is not None:
                    fvg_low, fvg_high = active_bearish_fvg
                    # Price rallied into FVG zone
                    if df["High"].iloc[i] >= fvg_low and df["Close"].iloc[i] < fvg_high:
                        if df["Bias"].iloc[i] <= 0:
                            df.iloc[i, df.columns.get_loc("Signal")] = -1
                            active_bearish_fvg = None  # FVG filled
        
        return df
