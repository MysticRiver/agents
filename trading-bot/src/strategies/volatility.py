"""Volatility-based trading strategies"""
import pandas as pd
import numpy as np
from .base import BaseStrategy
from loguru import logger


class ATRBreakoutStrategy(BaseStrategy):
    """
    ATR Breakout Strategy
    
    Enters when price moves beyond a multiple of ATR from recent levels.
    Designed to capture volatility expansion moves.
    """
    
    def __init__(
        self,
        atr_period: int = 14,
        atr_multiplier: float = 2.0,
        lookback_period: int = 10,
        use_close: bool = True,
        require_volume_confirmation: bool = True,
        volume_multiplier: float = 1.5,
        trailing_stop_atr: float = 2.0
    ):
        super().__init__(
            name="ATR_Breakout",
            atr_period=atr_period,
            atr_multiplier=atr_multiplier,
            lookback_period=lookback_period,
            use_close=use_close,
            require_volume_confirmation=require_volume_confirmation,
            volume_multiplier=volume_multiplier,
            trailing_stop_atr=trailing_stop_atr
        )
        self.atr_period = atr_period
        self.atr_multiplier = atr_multiplier
        self.lookback_period = lookback_period
        self.use_close = use_close
        self.require_volume_confirmation = require_volume_confirmation
        self.volume_multiplier = volume_multiplier
        self.trailing_stop_atr = trailing_stop_atr
        
    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """Generate signals based on ATR breakouts"""
        if not self._validate_data(data):
            raise ValueError("Invalid data")
            
        df = data.copy()
        
        # Calculate ATR
        df["ATR"] = self.calculate_atr(df, self.atr_period)
        
        # Calculate breakout levels
        if self.use_close:
            df["Reference"] = df["Close"].rolling(window=self.lookback_period).mean()
        else:
            df["Reference"] = (
                df["High"].rolling(window=self.lookback_period).max() +
                df["Low"].rolling(window=self.lookback_period).min()
            ) / 2
        
        df["Upper_Breakout"] = df["Reference"] + (df["ATR"] * self.atr_multiplier)
        df["Lower_Breakout"] = df["Reference"] - (df["ATR"] * self.atr_multiplier)
        
        # Volume confirmation
        df["Volume_SMA"] = df["Volume"].rolling(window=20).mean()
        df["Volume_Ratio"] = df["Volume"] / df["Volume_SMA"]
        
        # ATR expansion indicator (volatility increasing)
        df["ATR_SMA"] = df["ATR"].rolling(window=20).mean()
        df["ATR_Expansion"] = df["ATR"] > df["ATR_SMA"]
        
        # Initialize signals
        df["Signal"] = 0
        
        # Breakout conditions
        long_breakout = df["Close"] > df["Upper_Breakout"].shift(1)
        short_breakout = df["Close"] < df["Lower_Breakout"].shift(1)
        
        # Apply filters
        if self.require_volume_confirmation:
            volume_ok = df["Volume_Ratio"] > self.volume_multiplier
            long_breakout = long_breakout & volume_ok
            short_breakout = short_breakout & volume_ok
        
        # Require volatility expansion for better breakouts
        long_breakout = long_breakout & df["ATR_Expansion"]
        short_breakout = short_breakout & df["ATR_Expansion"]
        
        df.loc[long_breakout, "Signal"] = 1
        df.loc[short_breakout, "Signal"] = -1
        
        # Stop loss and take profit
        df["StopLoss"] = np.nan
        df["TakeProfit"] = np.nan
        
        df.loc[df["Signal"] == 1, "StopLoss"] = df["Close"] - (df["ATR"] * self.trailing_stop_atr)
        df.loc[df["Signal"] == 1, "TakeProfit"] = df["Close"] + (df["ATR"] * self.trailing_stop_atr * 2)
        
        df.loc[df["Signal"] == -1, "StopLoss"] = df["Close"] + (df["ATR"] * self.trailing_stop_atr)
        df.loc[df["Signal"] == -1, "TakeProfit"] = df["Close"] - (df["ATR"] * self.trailing_stop_atr * 2)
        
        df["StopLoss"] = df["StopLoss"].ffill()
        df["TakeProfit"] = df["TakeProfit"].ffill()
        
        return df


class RangeExpansionStrategy(BaseStrategy):
    """
    Range Expansion Strategy
    
    Identifies when the trading range expands after contraction.
    Uses Inside Bar patterns and subsequent breakouts.
    """
    
    def __init__(
        self,
        inside_bar_lookback: int = 3,
        breakout_multiplier: float = 0.5,
        atr_period: int = 14,
        min_contraction_ratio: float = 0.6,
        require_trend_alignment: bool = True,
        trend_period: int = 50
    ):
        super().__init__(
            name="Range_Expansion",
            inside_bar_lookback=inside_bar_lookback,
            breakout_multiplier=breakout_multiplier,
            atr_period=atr_period,
            min_contraction_ratio=min_contraction_ratio,
            require_trend_alignment=require_trend_alignment,
            trend_period=trend_period
        )
        self.inside_bar_lookback = inside_bar_lookback
        self.breakout_multiplier = breakout_multiplier
        self.atr_period = atr_period
        self.min_contraction_ratio = min_contraction_ratio
        self.require_trend_alignment = require_trend_alignment
        self.trend_period = trend_period
        
    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """Generate signals based on range expansion"""
        if not self._validate_data(data):
            raise ValueError("Invalid data")
            
        df = data.copy()
        
        # Calculate range metrics
        df["Range"] = df["High"] - df["Low"]
        df["Avg_Range"] = df["Range"].rolling(window=20).mean()
        df["Range_Ratio"] = df["Range"] / df["Avg_Range"]
        
        # ATR for stops
        df["ATR"] = self.calculate_atr(df, self.atr_period)
        
        # Trend filter
        df["Trend_SMA"] = self.calculate_sma(df["Close"], self.trend_period)
        df["Uptrend"] = df["Close"] > df["Trend_SMA"]
        df["Downtrend"] = df["Close"] < df["Trend_SMA"]
        
        # Identify inside bars (range contraction)
        df["Inside_Bar"] = (
            (df["High"] < df["High"].shift(1)) &
            (df["Low"] > df["Low"].shift(1))
        )
        
        # Identify narrow range bars (NR4, NR7 patterns)
        df["NR4"] = df["Range"] == df["Range"].rolling(window=4).min()
        df["NR7"] = df["Range"] == df["Range"].rolling(window=7).min()
        
        # Range contraction pattern
        df["Contraction"] = (
            df["Inside_Bar"] | 
            df["NR4"] | 
            (df["Range_Ratio"] < self.min_contraction_ratio)
        )
        
        # Contraction followed by expansion
        df["Recent_Contraction"] = df["Contraction"].rolling(window=self.inside_bar_lookback).sum() >= 1
        
        # Breakout levels from mother bar or recent range
        df["Mother_High"] = df["High"].rolling(window=self.inside_bar_lookback).max()
        df["Mother_Low"] = df["Low"].rolling(window=self.inside_bar_lookback).min()
        
        # Initialize signals
        df["Signal"] = 0
        
        # Long breakout: price breaks above mother bar high after contraction
        long_breakout = (
            df["Recent_Contraction"].shift(1) &
            (df["Close"] > df["Mother_High"].shift(1)) &
            (df["Range_Ratio"] > 1.0)  # Expansion occurring
        )
        
        # Short breakout: price breaks below mother bar low after contraction
        short_breakout = (
            df["Recent_Contraction"].shift(1) &
            (df["Close"] < df["Mother_Low"].shift(1)) &
            (df["Range_Ratio"] > 1.0)  # Expansion occurring
        )
        
        # Apply trend filter if enabled
        if self.require_trend_alignment:
            long_breakout = long_breakout & df["Uptrend"]
            short_breakout = short_breakout & df["Downtrend"]
        
        df.loc[long_breakout, "Signal"] = 1
        df.loc[short_breakout, "Signal"] = -1
        
        # Stop loss and take profit
        df["StopLoss"] = np.nan
        df["TakeProfit"] = np.nan
        
        # For longs: stop at mother bar low
        df.loc[df["Signal"] == 1, "StopLoss"] = df["Mother_Low"] - (df["ATR"] * 0.5)
        df.loc[df["Signal"] == 1, "TakeProfit"] = df["Close"] + (df["ATR"] * 3)
        
        # For shorts: stop at mother bar high
        df.loc[df["Signal"] == -1, "StopLoss"] = df["Mother_High"] + (df["ATR"] * 0.5)
        df.loc[df["Signal"] == -1, "TakeProfit"] = df["Close"] - (df["ATR"] * 3)
        
        df["StopLoss"] = df["StopLoss"].ffill()
        df["TakeProfit"] = df["TakeProfit"].ffill()
        
        return df


class KeltnerChannelStrategy(BaseStrategy):
    """
    Keltner Channel Breakout Strategy
    
    Uses Keltner Channels (EMA + ATR bands) for volatility breakouts.
    Combines trend following with volatility filters.
    """
    
    def __init__(
        self,
        ema_period: int = 20,
        atr_period: int = 14,
        atr_multiplier: float = 2.0,
        require_close_outside: bool = True,
        squeeze_filter: bool = True,
        squeeze_bb_period: int = 20,
        squeeze_bb_std: float = 2.0
    ):
        super().__init__(
            name="Keltner_Channel",
            ema_period=ema_period,
            atr_period=atr_period,
            atr_multiplier=atr_multiplier,
            require_close_outside=require_close_outside,
            squeeze_filter=squeeze_filter,
            squeeze_bb_period=squeeze_bb_period,
            squeeze_bb_std=squeeze_bb_std
        )
        self.ema_period = ema_period
        self.atr_period = atr_period
        self.atr_multiplier = atr_multiplier
        self.require_close_outside = require_close_outside
        self.squeeze_filter = squeeze_filter
        self.squeeze_bb_period = squeeze_bb_period
        self.squeeze_bb_std = squeeze_bb_std
        
    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """Generate signals based on Keltner Channel breakouts"""
        if not self._validate_data(data):
            raise ValueError("Invalid data")
            
        df = data.copy()
        
        # Calculate Keltner Channel
        df["KC_Middle"] = self.calculate_ema(df["Close"], self.ema_period)
        df["ATR"] = self.calculate_atr(df, self.atr_period)
        df["KC_Upper"] = df["KC_Middle"] + (df["ATR"] * self.atr_multiplier)
        df["KC_Lower"] = df["KC_Middle"] - (df["ATR"] * self.atr_multiplier)
        
        # Calculate Bollinger Bands for squeeze detection
        if self.squeeze_filter:
            bb_upper, bb_middle, bb_lower = self.calculate_bollinger_bands(
                df["Close"], self.squeeze_bb_period, self.squeeze_bb_std
            )
            df["BB_Upper"] = bb_upper
            df["BB_Lower"] = bb_lower
            
            # Squeeze: BB inside KC (low volatility)
            df["In_Squeeze"] = (df["BB_Lower"] > df["KC_Lower"]) & (df["BB_Upper"] < df["KC_Upper"])
            df["Squeeze_Release"] = df["In_Squeeze"].shift(1) & ~df["In_Squeeze"]
        
        # Initialize signals
        df["Signal"] = 0
        
        # Breakout conditions
        if self.require_close_outside:
            long_breakout = df["Close"] > df["KC_Upper"]
            short_breakout = df["Close"] < df["KC_Lower"]
        else:
            long_breakout = df["High"] > df["KC_Upper"]
            short_breakout = df["Low"] < df["KC_Lower"]
        
        # Apply squeeze filter if enabled (trade only on squeeze release)
        if self.squeeze_filter:
            # Enter when coming out of squeeze
            long_breakout = long_breakout & (df["Squeeze_Release"] | ~df["In_Squeeze"])
            short_breakout = short_breakout & (df["Squeeze_Release"] | ~df["In_Squeeze"])
        
        df.loc[long_breakout, "Signal"] = 1
        df.loc[short_breakout, "Signal"] = -1
        
        # Stop loss and take profit
        df["StopLoss"] = np.nan
        df["TakeProfit"] = np.nan
        
        df.loc[df["Signal"] == 1, "StopLoss"] = df["KC_Middle"]
        df.loc[df["Signal"] == 1, "TakeProfit"] = df["Close"] + (df["ATR"] * 3)
        
        df.loc[df["Signal"] == -1, "StopLoss"] = df["KC_Middle"]
        df.loc[df["Signal"] == -1, "TakeProfit"] = df["Close"] - (df["ATR"] * 3)
        
        df["StopLoss"] = df["StopLoss"].ffill()
        df["TakeProfit"] = df["TakeProfit"].ffill()
        
        return df
